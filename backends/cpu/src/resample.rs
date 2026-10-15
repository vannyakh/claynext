/// High-performance linear audio interpolation resampler
pub fn resample_linear(input: &[f32], src_rate: u32, dst_rate: u32) -> Vec<f32> {
    if src_rate == dst_rate || input.is_empty() {
        return input.to_vec();
    }

    let ratio = src_rate as f64 / dst_rate as f64;
    let out_len = ((input.len() as f64) / ratio).round() as usize;
    let mut output = Vec::with_capacity(out_len);

    for i in 0..out_len {
        let src_pos = i as f64 * ratio;
        let idx0 = src_pos.floor() as usize;
        let frac = (src_pos - idx0 as f64) as f32;

        if idx0 >= input.len() - 1 {
            if idx0 < input.len() {
                output.push(input[idx0]);
            }
            break;
        }

        let s0 = input[idx0];
        let s1 = input[idx0 + 1];
        output.push(s0 + frac * (s1 - s0));
    }

    output
}
