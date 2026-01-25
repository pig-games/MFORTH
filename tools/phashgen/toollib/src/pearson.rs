pub const AUX_TABLE_SIZE: usize = 256;

pub struct PearsonHashFunction {
    aux_table: [u8; AUX_TABLE_SIZE],
}

impl PearsonHashFunction {
    pub fn new(rng: &mut impl DotNetRand) -> Self {
        let mut table = [0u8; AUX_TABLE_SIZE];
        for (i, val) in table.iter_mut().enumerate() {
            *val = i as u8;
        }
        shuffle(&mut table, rng);
        Self { aux_table: table }
    }

    pub fn shuffle(&mut self, rng: &mut impl DotNetRand) {
        shuffle(&mut self.aux_table, rng);
    }

    pub fn hash(&self, buf: &[u8]) -> u8 {
        let mut hash = 0u8;
        for &b in buf {
            hash = self.aux_table[(hash ^ b) as usize];
        }
        hash
    }

    pub fn aux_table(&self) -> &[u8; AUX_TABLE_SIZE] {
        &self.aux_table
    }
}

pub trait DotNetRand {
    fn next(&mut self, max_exclusive: usize) -> usize;
}

fn shuffle<T: Copy>(array: &mut [T], rng: &mut impl DotNetRand) {
    for i in (1..=array.len()).rev() {
        let j = rng.next(i);
        array.swap(j, i - 1);
    }
}

pub fn uppercase_bytes(s: &str) -> Vec<u8> {
    s.to_ascii_uppercase().into_bytes()
}

pub fn hash_name(
    name: &str,
    phf1: &PearsonHashFunction,
    phf2: &PearsonHashFunction,
    mask: u16,
) -> u16 {
    let bytes = uppercase_bytes(name);
    let h1 = phf1.hash(&bytes) as u16;
    let h2 = phf2.hash(&bytes) as u16;
    ((h1 << 8) | h2) & mask
}

pub fn hash_name_swapped(
    name: &str,
    phf1: &PearsonHashFunction,
    phf2: &PearsonHashFunction,
    mask: u16,
) -> u16 {
    let bytes = uppercase_bytes(name);
    let h1 = phf2.hash(&bytes) as u16;
    let h2 = phf1.hash(&bytes) as u16;
    ((h1 << 8) | h2) & mask
}

pub struct DotNetRandom {
    inext: usize,
    inextp: usize,
    seed_array: [i32; 56],
}

impl DotNetRandom {
    pub fn new(seed: i32) -> Self {
        const MBIG: i32 = 2147483647;
        const MSEED: i32 = 161803398;
        let mut seed_array = [0i32; 56];
        let mut mj = MSEED - seed.abs();
        if mj < 0 {
            mj += MBIG;
        }
        seed_array[55] = mj;
        let mut mk = 1;
        for i in 1..55 {
            let ii = (21 * i) % 55;
            seed_array[ii] = mk;
            mk = mj - mk;
            if mk < 0 {
                mk += MBIG;
            }
            mj = seed_array[ii];
        }
        for _ in 0..4 {
            for i in 1..56 {
                seed_array[i] -= seed_array[1 + (i + 30) % 55];
                if seed_array[i] < 0 {
                    seed_array[i] += MBIG;
                }
            }
        }
        Self {
            inext: 0,
            inextp: 21,
            seed_array,
        }
    }

    fn internal_sample(&mut self) -> i32 {
        const MBIG: i32 = 2147483647;
        let mut inext = self.inext + 1;
        let mut inextp = self.inextp + 1;
        if inext >= 56 {
            inext = 1;
        }
        if inextp >= 56 {
            inextp = 1;
        }
        let mut ret = self.seed_array[inext] - self.seed_array[inextp];
        if ret < 0 {
            ret += MBIG;
        }
        self.seed_array[inext] = ret;
        self.inext = inext;
        self.inextp = inextp;
        ret
    }

    fn sample(&mut self) -> f64 {
        const MBIG: f64 = 2147483647.0;
        self.internal_sample() as f64 * (1.0 / MBIG)
    }
}

impl DotNetRand for DotNetRandom {
    fn next(&mut self, max_exclusive: usize) -> usize {
        if max_exclusive <= 1 {
            return 0;
        }
        (self.sample() * max_exclusive as f64) as usize
    }
}
