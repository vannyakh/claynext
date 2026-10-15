//! claynext-engine: Native Rust CLI command executor for Python PySide6 frontend.

use editor_api::{Command, CommandResult};
use editor_core::Engine;
use std::env;
use std::io::{self, BufRead};

fn main() {
    env_logger::init();
    let engine = Engine::new();
    let args: Vec<String> = env::args().collect();

    // Mode 1: Execute single JSON command from CLI argument
    if args.len() >= 3 && args[1] == "exec" {
        let json_cmd = &args[2];
        match serde_json::from_str::<Command>(json_cmd) {
            Ok(cmd) => {
                let result = engine.dispatch(cmd);
                println!("{}", serde_json::to_string(&result).unwrap());
            }
            Err(e) => {
                let err = CommandResult::err("PARSE_ERROR", e.to_string());
                println!("{}", serde_json::to_string(&err).unwrap());
            }
        }
        return;
    }

    // Mode 2: Interactive stream mode via standard input (line-delimited JSON commands)
    let stdin = io::stdin();
    for line in stdin.lock().lines() {
        match line {
            Ok(content) => {
                let trimmed = content.trim();
                if trimmed.is_empty() {
                    continue;
                }
                if trimmed == "exit" || trimmed == "quit" {
                    break;
                }
                match serde_json::from_str::<Command>(trimmed) {
                    Ok(cmd) => {
                        let result = engine.dispatch(cmd);
                        println!("{}", serde_json::to_string(&result).unwrap());
                    }
                    Err(e) => {
                        let err = CommandResult::err("PARSE_ERROR", e.to_string());
                        println!("{}", serde_json::to_string(&err).unwrap());
                    }
                }
            }
            Err(_) => break,
        }
    }
}
