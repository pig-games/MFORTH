use crate::errors::{Result, ToolLibError};
use crate::rom::Rom;

#[derive(Clone)]
pub struct Word {
    pub name: String,
    pub nfa: u16,
    pub next_word_addr: u16,
}

impl Word {
    const NFATOLFASZ: usize = 1;

    pub fn from_rom(rom: &Rom, nfa: u16) -> Result<Self> {
        let name = Self::read_name(rom, nfa as usize)?;
        let next_word_addr = rom.get_u16(nfa as usize + Self::NFATOLFASZ) as u16;
        Ok(Self {
            name,
            nfa,
            next_word_addr,
        })
    }

    fn read_name(rom: &Rom, nfa: usize) -> Result<String> {
        let word_len = (rom.get_u8(nfa) & 0x3F) as usize;
        let mut bytes = Vec::new();
        let mut offset = nfa.wrapping_sub(1);
        loop {
            let c = rom.get_u8(offset);
            bytes.push(c & 0x7F);
            if (c & 0x80) != 0 {
                break;
            }
            offset = offset.wrapping_sub(1);
        }
        let name = String::from_utf8(bytes)
            .map_err(|e| ToolLibError::Message(format!("invalid word name encoding: {e}")))?;
        if name.len() != word_len {
            return Err(ToolLibError::Message(format!(
                "Word '{0}' has NFA with incorrect length {1}.",
                name, word_len
            )));
        }
        Ok(name)
    }
}
