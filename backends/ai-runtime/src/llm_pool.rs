use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiKeyItem {
    pub id: i64,
    pub provider: String,
    pub secret: String,
    #[serde(default)]
    pub label: String,
    #[serde(default = "default_enabled")]
    pub enabled: bool,
    pub cooldown_until: Option<f64>,
    #[serde(default)]
    pub fail_count: i32,
    pub last_used_at: Option<f64>,
}

fn default_enabled() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RateLimitDecision {
    pub is_rate_limit: bool,
    pub retry_after_secs: f64,
}

pub fn now_epoch() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

pub fn is_rate_limit_status(status: u16, body: &str) -> bool {
    if status == 429 {
        return true;
    }
    let lower = body.to_lowercase();
    lower.contains("resource_exhausted")
        || lower.contains("rate limit")
        || (lower.contains("quota") && lower.contains("exceed"))
        || lower.contains("too many requests")
}

pub fn parse_retry_after(header: Option<&str>, body: &str) -> f64 {
    let mut seconds = 20.0f64;
    if let Some(h) = header {
        let trimmed = h.trim();
        if let Ok(val) = trimmed.parse::<f64>() {
            seconds = val;
        }
    }

    let lower = body.to_lowercase();
    if let Some(idx) = lower.find("retry") {
        let slice = &lower[idx..];
        let mut num_str = String::new();
        let mut recording = false;
        for ch in slice.chars() {
            if ch.is_ascii_digit() || (ch == '.' && !num_str.contains('.')) {
                recording = true;
                num_str.push(ch);
            } else if recording {
                break;
            }
        }
        if let Ok(parsed) = num_str.parse::<f64>() {
            if parsed > seconds {
                seconds = parsed;
            }
        }
    }

    seconds.clamp(5.0, 120.0)
}

#[derive(Default)]
pub struct NativeKeyPool {
    cursor: Mutex<HashMap<String, usize>>,
}

impl NativeKeyPool {
    pub fn new() -> Self {
        Self {
            cursor: Mutex::new(HashMap::new()),
        }
    }

    pub fn filter_ready_keys<'a>(
        &self,
        keys: &'a [ApiKeyItem],
        provider: &str,
        now: f64,
    ) -> Vec<&'a ApiKeyItem> {
        keys.iter()
            .filter(|k| {
                k.provider.eq_ignore_ascii_case(provider)
                    && k.enabled
                    && !k.secret.trim().is_empty()
                    && k.cooldown_until.is_none_or(|c| c <= now)
            })
            .collect()
    }

    pub fn acquire_key<'a>(
        &self,
        keys: &'a [ApiKeyItem],
        provider: &str,
    ) -> Option<&'a ApiKeyItem> {
        let now = now_epoch();
        let ready = self.filter_ready_keys(keys, provider, now);
        if ready.is_empty() {
            return None;
        }

        let mut lock = self.cursor.lock().unwrap();
        let current_idx = *lock.get(provider).unwrap_or(&0);
        let selected_idx = current_idx % ready.len();
        lock.insert(provider.to_string(), (selected_idx + 1) % ready.len());

        Some(ready[selected_idx])
    }

    pub fn soonest_cooldown(&self, keys: &[ApiKeyItem], provider: &str) -> f64 {
        let now = now_epoch();
        let mut min_wait = f64::MAX;
        let mut found = false;

        for k in keys {
            if k.provider.eq_ignore_ascii_case(provider) && k.enabled {
                if let Some(until) = k.cooldown_until {
                    if until > now {
                        let wait = until - now;
                        if wait < min_wait {
                            min_wait = wait;
                            found = true;
                        }
                    }
                }
            }
        }

        if found {
            min_wait
        } else {
            0.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rate_limit_detection() {
        assert!(is_rate_limit_status(429, ""));
        assert!(is_rate_limit_status(200, "RESOURCE_EXHAUSTED: quota exceeded"));
        assert!(!is_rate_limit_status(200, "ok"));
    }

    #[test]
    fn test_retry_after_parsing() {
        assert_eq!(parse_retry_after(Some("45"), ""), 45.0);
        assert_eq!(parse_retry_after(None, "Please retry after 32.5 seconds"), 32.5);
        assert_eq!(parse_retry_after(Some("2"), ""), 5.0); // clamped min 5.0
    }

    #[test]
    fn test_key_pool_rotation() {
        let pool = NativeKeyPool::new();
        let keys = vec![
            ApiKeyItem {
                id: 1,
                provider: "gemini".to_string(),
                secret: "AIza1".to_string(),
                label: "Key 1".to_string(),
                enabled: true,
                cooldown_until: None,
                fail_count: 0,
                last_used_at: None,
            },
            ApiKeyItem {
                id: 2,
                provider: "gemini".to_string(),
                secret: "AIza2".to_string(),
                label: "Key 2".to_string(),
                enabled: true,
                cooldown_until: None,
                fail_count: 0,
                last_used_at: None,
            },
        ];

        let first = pool.acquire_key(&keys, "gemini").unwrap();
        assert_eq!(first.id, 1);
        let second = pool.acquire_key(&keys, "gemini").unwrap();
        assert_eq!(second.id, 2);
        let third = pool.acquire_key(&keys, "gemini").unwrap();
        assert_eq!(third.id, 1);
    }
}
