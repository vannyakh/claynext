use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TextureDescriptor {
    pub width: u32,
    pub height: u32,
    pub format: String,
    pub usage: u32,
}

impl TextureDescriptor {
    pub fn new_rgba(width: u32, height: u32) -> Self {
        Self {
            width,
            height,
            format: "Rgba8Unorm".to_string(),
            usage: 0x01 | 0x02 | 0x04 | 0x08, // COPY_SRC | COPY_DST | TEXTURE_BINDING | STORAGE_BINDING
        }
    }

    pub fn size_bytes(&self) -> usize {
        (self.width * self.height * 4) as usize
    }
}
