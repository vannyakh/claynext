pub fn build_loudnorm_filter(integrated_lufs: f64, true_peak_db: f64) -> String {
    format!(
        "loudnorm=I={:.1}:TP={:.1}:LRA=11",
        integrated_lufs, true_peak_db
    )
}

pub fn build_sidechain_ducking_filter(duck_ratio: f64, threshold_db: f64) -> String {
    format!(
        "[0:a][1:a]sidechaincompress=threshold={:.1}dB:ratio={:.1}:attack=20:release=250[ducked]",
        threshold_db, duck_ratio
    )
}
