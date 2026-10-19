//! How many dub jobs and voice workers this machine should run at once.
use serde::Serialize;
use std::process::Command;
use std::thread;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct HardwarePlan {
    pub logical_cores: usize,
    pub physical_cores: usize,
    pub reserve_cores: usize,
    pub dub_jobs: usize,
    pub tts_workers: usize,
}

/// Keep this formula in sync with `claynext.adapters.cpu.plan_for`.
pub fn plan_for(logical: usize, physical: usize) -> HardwarePlan {
    let logical = logical.max(1);
    let physical = physical.clamp(1, logical);
    let reserve_cores = if logical > 4 { 2 } else { 1 };
    let usable = logical.saturating_sub(reserve_cores).max(1);
    // Each movie loads its own speech model. One job per three physical cores.
    let dub_jobs = (physical / 3).clamp(1, 4);
    let tts_workers = if logical == 1 {
        1
    } else if dub_jobs == 1 {
        usable.clamp(2, 8)
    } else {
        (usable / dub_jobs).clamp(2, 4)
    };
    HardwarePlan {
        logical_cores: logical,
        physical_cores: physical,
        reserve_cores,
        dub_jobs,
        tts_workers,
    }
}

pub fn logical_cores() -> usize {
    thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(1)
        .max(1)
}

pub fn physical_cores(logical: usize) -> usize {
    if let Some(cores) = read_physical() {
        return cores.clamp(1, logical.max(1));
    }
    if logical >= 4 && logical % 2 == 0 {
        logical / 2
    } else {
        logical.max(1)
    }
}

fn read_physical() -> Option<usize> {
    #[cfg(target_os = "macos")]
    {
        let out = Command::new("sysctl")
            .args(["-n", "hw.physicalcpu"])
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        return String::from_utf8(out.stdout).ok()?.trim().parse().ok();
    }
    #[cfg(target_os = "linux")]
    {
        let text = std::fs::read_to_string("/proc/cpuinfo").ok()?;
        for line in text.lines() {
            let (key, value) = line.split_once(':')?;
            if key.trim() == "cpu cores" {
                return value.trim().parse().ok();
            }
        }
        return None;
    }
    #[cfg(not(any(target_os = "macos", target_os = "linux")))]
    {
        None
    }
}

pub fn current_plan() -> HardwarePlan {
    let logical = logical_cores();
    plan_for(logical, physical_cores(logical))
}

pub fn plan_json() -> String {
    serde_json::to_string(&current_plan()).unwrap_or_else(|_| "{}".to_string())
}

#[cfg(test)]
mod tests {
    use super::plan_for;

    #[test]
    fn laptop_six_cores_runs_two_movies() {
        let plan = plan_for(12, 6);
        assert_eq!(plan.dub_jobs, 2);
        assert_eq!(plan.tts_workers, 4);
        assert_eq!(plan.reserve_cores, 2);
    }

    #[test]
    fn small_machine_stays_on_one_movie() {
        let plan = plan_for(4, 2);
        assert_eq!(plan.dub_jobs, 1);
        assert!(plan.tts_workers >= 1);
    }

    #[test]
    fn single_core_is_serial() {
        let plan = plan_for(1, 1);
        assert_eq!(plan.dub_jobs, 1);
        assert_eq!(plan.tts_workers, 1);
    }
}
