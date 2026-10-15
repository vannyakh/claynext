pub mod asr;
pub mod error;
pub mod expression;
pub mod tts;
pub mod voice_activity;
pub mod voice_detection;

pub use asr::{AsrOptions, AsrSegment, AsrWord};
pub use error::SpeechError;
pub use expression::{parse_expression_tags, UtteranceSegment};
pub use tts::{TtsRequest, TtsVoice};
pub use voice_activity::{SpeechSpan, VadParameters};
pub use voice_detection::{estimate_gender_from_pitch, VoiceClassificationResult, VoiceGender};
