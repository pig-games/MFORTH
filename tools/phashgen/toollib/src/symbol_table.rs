use crate::errors::{Result, ToolLibError};
use std::collections::HashMap;
use std::path::Path;

pub fn load_symbol_table(path: &Path) -> Result<HashMap<u16, String>> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| ToolLibError::Message(format!("failed to read symbol table: {e}")))?;
    let mut map = HashMap::new();
    for line in content.lines() {
        let mut parts = line.splitn(2, ' ');
        let name = parts.next().unwrap_or("").trim();
        let addr_str = parts.next().unwrap_or("").trim();
        if name.is_empty() || addr_str.is_empty() {
            continue;
        }
        if name.starts_with("noname.") || name.starts_with("LINK_") || name.starts_with("LAST_") {
            continue;
        }
        let addr = u16::from_str_radix(addr_str, 16).map_err(|e| {
            ToolLibError::Message(format!("invalid symbol address '{addr_str}': {e}"))
        })?;
        map.insert(addr, name.to_string());
    }
    Ok(map)
}
