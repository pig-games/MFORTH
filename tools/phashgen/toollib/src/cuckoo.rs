use std::collections::HashMap;

pub struct CuckooHashTable<T, F1, F2>
where
    F1: Fn(&T) -> u16,
    F2: Fn(&T) -> u16,
{
    hash1: F1,
    hash2: F2,
    table: HashMap<u16, Entry<T>>,
    pub num_values_at_first: usize,
    pub num_values_at_second: usize,
}

struct Entry<T> {
    hash1: u16,
    hash2: u16,
    value: T,
    seen: bool,
}

impl<T, F1, F2> CuckooHashTable<T, F1, F2>
where
    F1: Fn(&T) -> u16,
    F2: Fn(&T) -> u16,
{
    pub fn new(hash1: F1, hash2: F2) -> Self {
        Self {
            hash1,
            hash2,
            table: HashMap::new(),
            num_values_at_first: 0,
            num_values_at_second: 0,
        }
    }

    pub fn clear(&mut self) {
        self.table.clear();
        self.num_values_at_first = 0;
        self.num_values_at_second = 0;
    }

    pub fn count(&self) -> usize {
        self.table.len()
    }

    pub fn try_get(&self, key: u16) -> Option<&T> {
        self.table.get(&key).map(|e| &e.value)
    }

    pub fn try_add(&mut self, value: T) -> bool {
        let h1 = (self.hash1)(&value);
        let h2 = (self.hash2)(&value);
        let entry = Entry {
            hash1: h1,
            hash2: h2,
            value,
            seen: false,
        };

        if !self.table.contains_key(&entry.hash1) {
            self.table.insert(entry.hash1, entry);
            self.num_values_at_first += 1;
            return true;
        }

        for existing in self.table.values_mut() {
            existing.seen = false;
        }

        self.try_assign_and_kick(entry)
    }

    fn try_assign_and_kick(&mut self, mut entry: Entry<T>) -> bool {
        loop {
            if !self.table.contains_key(&entry.hash2) {
                self.table.insert(entry.hash2, entry);
                self.num_values_at_second += 1;
                return true;
            }

            let mut kicked = match self.table.remove(&entry.hash2) {
                Some(k) => k,
                None => return false,
            };

            if kicked.seen {
                self.table.insert(kicked.hash2, kicked);
                return false;
            }

            self.table.insert(entry.hash2, Entry {
                seen: true,
                ..entry
            });
            self.num_values_at_first = self.num_values_at_first.saturating_sub(1);
            self.num_values_at_second += 1;

            kicked.seen = true;
            entry = kicked;
        }
    }
}
