use crate::errors::{Result, ToolLibError};
use crate::word::Word;
use std::collections::HashMap;

pub struct Rom {
    bytes: Vec<u8>,
}

impl Rom {
    pub const SIZE: usize = 0x8000;
    pub const LATEST_WORD_PTR_ADDR: usize = 0x7FFE;

    pub fn load(path: &std::path::Path) -> Result<Self> {
        let bytes = std::fs::read(path)
            .map_err(|e| ToolLibError::Message(format!("failed to read ROM: {e}")))?;
        if bytes.len() != Self::SIZE {
            return Err(ToolLibError::Message(format!(
                "MFORTH ROM was only {0} bytes long; expected {1} bytes.",
                bytes.len(),
                Self::SIZE
            )));
        }
        Ok(Self { bytes })
    }

    pub fn get_u8(&self, addr: usize) -> u8 {
        self.bytes[addr]
    }

    pub fn get_u16(&self, addr: usize) -> u16 {
        self.get_u8(addr) as u16 | ((self.get_u8(addr + 1) as u16) << 8)
    }

    pub fn latest_word_addr(&self) -> u16 {
        self.get_u16(Self::LATEST_WORD_PTR_ADDR)
    }

    pub fn words(&self) -> Result<Vec<Word>> {
        let mut words = Vec::new();
        let mut seen = HashMap::new();
        let mut cur = self.latest_word_addr();
        while cur != 0 {
            let word = Word::from_rom(self, cur)?;
            if seen.insert(word.name.clone(), true).is_some() {
                return Err(ToolLibError::Message(format!(
                    "Duplicate word name found in dictionary: {}",
                    word.name
                )));
            }
            cur = word.next_word_addr;
            words.push(word);
        }
        Ok(words)
    }
}
