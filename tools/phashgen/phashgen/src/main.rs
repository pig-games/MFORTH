use std::fs::File;
use std::io::{self, Write};
use std::path::PathBuf;

use anyhow::{anyhow, Context, Result};
use clap::Parser;
use toollib::cuckoo::CuckooHashTable;
use toollib::pearson::{hash_name, hash_name_swapped, DotNetRandom, PearsonHashFunction, AUX_TABLE_SIZE};
use toollib::rom::Rom;
use toollib::symbol_table::load_symbol_table;
use toollib::word::Word;

const HASH_TABLE_SIZE: usize = 1024;
const HASH_MASK: u16 = (HASH_TABLE_SIZE as u16) - 1;
const HASH_TABLE_RANDOM_SEED: i32 = 135960;

#[derive(Parser)]
struct Args {
    rom: PathBuf,
    sym: PathBuf,
    outasm: PathBuf,
}

fn main() -> Result<()> {
    let args = Args::parse();
    run(args)
}

fn run(args: Args) -> Result<()> {
    let rom = Rom::load(&args.rom).context("load ROM")?;
    let words = rom.words().context("load words")?;
    let symbols = load_symbol_table(&args.sym).context("load symbol table")?;

    print!("Generating PHASH tables: ");
    io::stdout().flush().ok();

    let mut rng = DotNetRandom::new(HASH_TABLE_RANDOM_SEED);
    let mut phf1 = PearsonHashFunction::new(&mut rng);
    let mut phf2 = PearsonHashFunction::new(&mut rng);

    let table = loop {
        print!(".");
        io::stdout().flush().ok();

        let mut table = CuckooHashTable::new(
            |w: &Word| hash_name(&w.name, &phf1, &phf2, HASH_MASK),
            |w: &Word| hash_name_swapped(&w.name, &phf1, &phf2, HASH_MASK),
        );

        let mut complete = true;
        for word in &words {
            if !table.try_add(word.clone()) {
                complete = false;
                break;
            }
        }

        if complete {
            println!(" Done!");
            if table.count() != words.len() {
                return Err(anyhow!(
                    "Hash table only has {0} words; expected {1} words.",
                    table.count(),
                    words.len()
                ));
            }
            break table;
        }

        drop(table);
        phf1.shuffle(&mut rng);
        phf2.shuffle(&mut rng);
    };

    println!(
        "Total words: {0}; at first hash location: {1}; at second hash location: {2}",
        words.len(),
        table.num_values_at_first,
        table.num_values_at_second
    );

    let mut out = File::create(&args.outasm).context("open output")?;
    write_header(&mut out, &rom)?;
    write_aux_table(&mut out, "PHASHAUX1", aux1_org(), phf1.aux_table())?;
    write_aux_table(&mut out, "PHASHAUX2", aux2_org(), phf2.aux_table())?;
    write_hash_table(&mut out, &table, &symbols)?;

    Ok(())
}

fn write_header(out: &mut dyn Write, _rom: &Rom) -> Result<()> {
    writeln!(out, "PHASHMASK   EQU    0{:02X}H", HASH_MASK >> 8)?;
    Ok(())
}

fn aux1_org() -> u16 {
    (Rom::SIZE - (HASH_TABLE_SIZE << 1) - (2 * AUX_TABLE_SIZE)) as u16
}

fn aux2_org() -> u16 {
    (Rom::SIZE - (HASH_TABLE_SIZE << 1) - AUX_TABLE_SIZE) as u16
}

fn tab_org() -> u16 {
    (Rom::SIZE - (HASH_TABLE_SIZE << 1)) as u16
}

fn write_aux_table(out: &mut dyn Write, label: &str, org: u16, bytes: &[u8]) -> Result<()> {
    writeln!(out, "            ORG    0{:04X}H", org)?;
    writeln!(out, "{}:", label)?;
    write_byte_data(out, bytes)?;
    Ok(())
}

fn write_byte_data(out: &mut dyn Write, bytes: &[u8]) -> Result<()> {
    for (i, b) in bytes.iter().enumerate() {
        if i % 8 == 0 {
            if i != 0 {
                writeln!(out)?;
            }
            write!(out, "            DB   ")?;
        } else {
            write!(out, ",")?;
        }
        write!(out, "{}", b)?;
    }
    writeln!(out)?;
    Ok(())
}

fn write_hash_table(
    out: &mut dyn Write,
    table: &CuckooHashTable<Word, impl Fn(&Word) -> u16, impl Fn(&Word) -> u16>,
    symbols: &std::collections::HashMap<u16, String>,
) -> Result<()> {
    writeln!(out, "            ORG    0{:04X}H", tab_org())?;
    writeln!(out, "PHASHTAB:")?;

    for i in 0..HASH_TABLE_SIZE {
        let key = i as u16;
        let Some(word) = table.try_get(key) else {
            writeln!(out, "            DW   0")?;
            continue;
        };

        let key1 = word.nfa.wrapping_add(3);
        let key2 = word.nfa.wrapping_add(5);
        let label = symbols
            .get(&key1)
            .or_else(|| symbols.get(&key2))
            .ok_or_else(|| anyhow!("missing symbol for word '{}'", word.name))?;

        writeln!(out, "            DW   {}-NFATOCFASZ", label)?;
    }

    Ok(())
}
