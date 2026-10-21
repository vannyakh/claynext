use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VadSegment {
    pub start_sec: f64,
    pub end_sec: f64,
    pub confidence: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VadConfig {
    pub threshold: f32,
    pub min_speech_duration_ms: u32,
    pub min_silence_duration_ms: u32,
    pub speech_pad_ms: u32,
}

impl Default for VadConfig {
    fn default() -> Self {
        Self {
            // Lower keeps quieter replies. 0.22 is the dubbing pass.
            threshold: 0.22,
            min_speech_duration_ms: 180,
            min_silence_duration_ms: 320,
            speech_pad_ms: 140,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TimedLine {
    pub start_sec: f64,
    pub end_sec: f64,
    #[serde(default)]
    pub text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FitSpeechRequest {
    #[serde(default)]
    pub lines: Vec<TimedLine>,
    #[serde(default)]
    pub turns: Vec<VadSegment>,
}

/// Speech turns that follow the soundtrack.
///
/// The floor sits just above the quiet part of the mix, so a soft reply is
/// kept and a pause still splits the next turn. Short breaths stay inside
/// the same turn; a real gap becomes the next voice segment.
pub fn energy_vad_chunking(
    samples: &[f32],
    sample_rate: u32,
    config: &VadConfig,
) -> Vec<VadSegment> {
    if samples.is_empty() || sample_rate == 0 {
        return Vec::new();
    }
    let frame = ((sample_rate as f32) * 0.03) as usize;
    if frame == 0 {
        return Vec::new();
    }
    let rms = frame_rms(samples, frame);
    if rms.is_empty() {
        return Vec::new();
    }
    let floor = speech_floor(&rms, config.threshold);
    let hang = ((config.min_silence_duration_ms as f32) / 30.0).ceil() as usize;
    let hang = hang.max(1);
    let min_frames = ((config.min_speech_duration_ms as f32) / 30.0).ceil() as usize;
    let pad = ((config.speech_pad_ms as f32) / 1000.0) as f64;

    let mut raw: Vec<(usize, usize)> = Vec::new();
    let mut in_speech = false;
    let mut start = 0usize;
    let mut quiet = 0usize;
    for (i, energy) in rms.iter().enumerate() {
        if *energy >= floor {
            if !in_speech {
                in_speech = true;
                start = i;
            }
            quiet = 0;
        } else if in_speech {
            quiet += 1;
            if quiet >= hang {
                let end = i + 1 - quiet;
                if end > start {
                    raw.push((start, end));
                }
                in_speech = false;
                quiet = 0;
            }
        }
    }
    if in_speech {
        raw.push((start, rms.len()));
    }

    let duration = samples.len() as f64 / sample_rate as f64;
    let mut turns: Vec<VadSegment> = Vec::new();
    for (start_f, end_f) in raw {
        if end_f.saturating_sub(start_f) < min_frames.max(1) {
            continue;
        }
        let start_sec = ((start_f * frame) as f64 / sample_rate as f64 - pad).max(0.0);
        let end_sec = (((end_f * frame) as f64 / sample_rate as f64) + pad).min(duration);
        if end_sec - start_sec < 0.12 {
            continue;
        }
        if let Some(prev) = turns.last_mut() {
            if start_sec - prev.end_sec <= 0.08 {
                prev.end_sec = prev.end_sec.max(end_sec);
                continue;
            }
        }
        turns.push(VadSegment {
            start_sec,
            end_sec,
            confidence: 0.85,
        });
    }
    turns
}

/// Place each transcript line on the soundtrack turn it belongs to.
///
/// One line in a turn is pulled onto that speech, up to a short pad, so the
/// voice clip meets the audio instead of floating inside it. Several lines
/// in one turn share that turn edge to edge. A line that spills across a
/// pause keeps only the turn it overlaps most.
pub fn fit_lines_to_speech(lines: &[TimedLine], turns: &[VadSegment]) -> Vec<TimedLine> {
    if lines.is_empty() || turns.is_empty() {
        return lines.to_vec();
    }
    let mut owners: Vec<Option<usize>> = vec![None; lines.len()];
    for (index, line) in lines.iter().enumerate() {
        let mut best: Option<(usize, f64)> = None;
        for (turn_i, turn) in turns.iter().enumerate() {
            let overlap = overlap(line.start_sec, line.end_sec, turn.start_sec, turn.end_sec);
            if overlap > 0.04 && best.map(|(_, score)| overlap > score).unwrap_or(true) {
                best = Some((turn_i, overlap));
            }
        }
        if best.is_none() {
            let mid = (line.start_sec + line.end_sec) * 0.5;
            let mut nearest: Option<(usize, f64)> = None;
            for (turn_i, turn) in turns.iter().enumerate() {
                let dist = if mid < turn.start_sec {
                    turn.start_sec - mid
                } else if mid > turn.end_sec {
                    mid - turn.end_sec
                } else {
                    0.0
                };
                if dist <= 0.7 && nearest.map(|(_, d)| dist < d).unwrap_or(true) {
                    nearest = Some((turn_i, dist));
                }
            }
            best = nearest.map(|(i, _)| (i, 0.0));
        }
        owners[index] = best.map(|(i, _)| i);
    }

    let mut out = lines.to_vec();
    let mut groups: Vec<Vec<usize>> = vec![Vec::new(); turns.len()];
    for (index, owner) in owners.iter().enumerate() {
        if let Some(turn_i) = owner {
            groups[*turn_i].push(index);
        }
    }
    for (turn_i, members) in groups.iter().enumerate() {
        if members.is_empty() {
            continue;
        }
        let turn = &turns[turn_i];
        if members.len() == 1 {
            let line = &mut out[members[0]];
            let start = (line.start_sec - 0.45).max(turn.start_sec).min(line.start_sec);
            let end = (line.end_sec + 0.45).min(turn.end_sec).max(line.end_sec);
            line.start_sec = start;
            line.end_sec = end.max(start + 0.12);
            continue;
        }
        let mut order = members.clone();
        order.sort_by(|&a, &b| {
            out[a]
                .start_sec
                .partial_cmp(&out[b].start_sec)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        let weights: Vec<f64> = order
            .iter()
            .map(|&i| (out[i].end_sec - out[i].start_sec).max(0.2))
            .collect();
        let total = weights.iter().sum::<f64>().max(0.2);
        let span = (turn.end_sec - turn.start_sec).max(0.12 * order.len() as f64);
        let mut cursor = turn.start_sec;
        for (n, &index) in order.iter().enumerate() {
            let share = if n + 1 == order.len() {
                turn.end_sec - cursor
            } else {
                (span * weights[n] / total).max(0.12)
            };
            let end = if n + 1 == order.len() {
                turn.end_sec
            } else {
                (cursor + share).min(turn.end_sec - 0.12 * (order.len() - n - 1) as f64)
            };
            out[index].start_sec = cursor;
            out[index].end_sec = end.max(cursor + 0.12);
            cursor = out[index].end_sec;
        }
    }
    out
}

fn frame_rms(samples: &[f32], frame: usize) -> Vec<f32> {
    let mut rms = Vec::with_capacity(samples.len() / frame);
    let mut i = 0;
    while i + frame <= samples.len() {
        let chunk = &samples[i..i + frame];
        let energy = chunk.iter().map(|s| s * s).sum::<f32>() / frame as f32;
        rms.push(energy.sqrt());
        i += frame;
    }
    rms
}

fn speech_floor(rms: &[f32], threshold: f32) -> f32 {
    let mut sorted = rms.to_vec();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let noise = sorted[(sorted.len().saturating_sub(1) * 20) / 100];
    let peak = sorted[(sorted.len().saturating_sub(1) * 92) / 100].max(noise + 1e-4);
    let sense = threshold.clamp(0.08, 0.85);
    // A low threshold keeps a quiet line; the floor still sits above the noise.
    let floor = noise + (peak - noise) * sense * 0.28;
    floor.max(0.008)
}

fn overlap(a0: f64, a1: f64, b0: f64, b1: f64) -> f64 {
    (a1.min(b1) - a0.max(b0)).max(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(buf: &mut [f32], from: usize, to: usize, amp: f32) {
        for (n, sample) in buf.iter_mut().enumerate().take(to).skip(from) {
            *sample = (n as f32 * 0.08).sin() * amp;
        }
    }

    #[test]
    fn two_spoken_turns_stay_split_across_a_pause() {
        let rate = 16_000u32;
        let mut samples = vec![0.0f32; rate as usize * 4];
        tone(&mut samples, rate as usize, rate as usize * 2, 0.45);
        tone(&mut samples, rate as usize * 3, rate as usize * 4, 0.2);
        let turns = energy_vad_chunking(&samples, rate, &VadConfig::default());
        assert!(
            turns.len() >= 2,
            "quiet reply must stay its own turn, got {turns:?}"
        );
    }

    #[test]
    fn a_breath_inside_one_line_does_not_split_the_turn() {
        let rate = 16_000u32;
        let mut samples = vec![0.0f32; rate as usize * 2];
        tone(&mut samples, 0, rate as usize, 0.4);
        tone(
            &mut samples,
            rate as usize + (rate as usize / 10),
            rate as usize * 2,
            0.4,
        );
        let turns = energy_vad_chunking(&samples, rate, &VadConfig::default());
        assert_eq!(turns.len(), 1, "80ms breath should stay one turn: {turns:?}");
    }

    #[test]
    fn one_line_is_pulled_onto_its_speech() {
        let turns = vec![VadSegment {
            start_sec: 1.0,
            end_sec: 2.4,
            confidence: 0.9,
        }];
        let lines = vec![TimedLine {
            start_sec: 1.35,
            end_sec: 2.0,
            text: "来了".into(),
        }];
        let fitted = fit_lines_to_speech(&lines, &turns);
        assert!((fitted[0].start_sec - 1.0).abs() < 0.05);
        assert!((fitted[0].end_sec - 2.4).abs() < 0.05);
    }

    #[test]
    fn two_lines_share_one_turn_without_a_hole() {
        let turns = vec![VadSegment {
            start_sec: 0.0,
            end_sec: 2.0,
            confidence: 0.9,
        }];
        let lines = vec![
            TimedLine {
                start_sec: 0.1,
                end_sec: 0.6,
                text: "你".into(),
            },
            TimedLine {
                start_sec: 0.9,
                end_sec: 1.4,
                text: "我".into(),
            },
        ];
        let fitted = fit_lines_to_speech(&lines, &turns);
        assert!((fitted[0].start_sec - 0.0).abs() < 0.05);
        assert!((fitted[1].end_sec - 2.0).abs() < 0.05);
        assert!((fitted[0].end_sec - fitted[1].start_sec).abs() < 0.05);
    }
}
