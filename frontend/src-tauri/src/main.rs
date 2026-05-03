// Prevent the extra console window on Windows in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;

use serde::Deserialize;
use tauri::api::process::{Command, CommandChild, CommandEvent};
use tauri::{Manager, RunEvent, WindowEvent};

#[derive(Default)]
struct SidecarState {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Deserialize)]
struct ReadyLine {
    #[serde(default = "default_host")]
    host: String,
    port: u16,
}

fn default_host() -> String {
    "127.0.0.1".into()
}

fn spawn_sidecar(app: &tauri::AppHandle) -> tauri::Result<CommandChild> {
    let resource_dir = app
        .path_resolver()
        .resource_dir()
        .expect("resource_dir not available");
    let app_data = app
        .path_resolver()
        .app_data_dir()
        .expect("app_data_dir not available");
    std::fs::create_dir_all(&app_data).ok();

    let audiveris = resource_dir.join("runtime/audiveris/bin/Audiveris");
    let java_home = resource_dir.join("runtime/jre");
    let tessdata = resource_dir.join("runtime/tessdata");
    let tess_bin = if cfg!(target_os = "windows") {
        resource_dir.join("tesseract/tesseract.exe")
    } else {
        resource_dir.join("tesseract/tesseract")
    };

    let (mut rx, child) = Command::new_sidecar("accompanist-server")
        .expect("failed to create sidecar command")
        .args([
            "--host", "127.0.0.1",
            "--port", "0",
            "--app-data", app_data.to_string_lossy().as_ref(),
        ])
        .envs([
            ("AUDIVERIS_LAUNCHER".to_string(), audiveris.to_string_lossy().into_owned()),
            ("JAVA_HOME".to_string(), java_home.to_string_lossy().into_owned()),
            ("TESSDATA_PREFIX".to_string(), tessdata.to_string_lossy().into_owned()),
            ("TESSERACT_CMD".to_string(), tess_bin.to_string_lossy().into_owned()),
            ("PIPELINE_PARAM_SET".to_string(), "v5_real_pdf".into()),
        ])
        .spawn()?;

    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => handle_stdout(&app_handle, &line),
                CommandEvent::Stderr(line) => eprintln!("[sidecar:err] {line}"),
                CommandEvent::Error(err) => eprintln!("[sidecar:fail] {err}"),
                CommandEvent::Terminated(payload) => {
                    eprintln!("[sidecar] exited code={:?}", payload.code);
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

fn handle_stdout(app: &tauri::AppHandle, line: &str) {
    if let Some(rest) = line.strip_prefix("READY ") {
        match serde_json::from_str::<ReadyLine>(rest.trim()) {
            Ok(ready) => {
                let url = format!("http://{}:{}", ready.host, ready.port);
                if let Some(window) = app.get_window("main") {
                    let script = format!("window.__BACKEND_URL__ = {};", serde_json::to_string(&url).unwrap());
                    let _ = window.eval(&script);
                }
                let _ = app.emit_all("backend-ready", &url);
                eprintln!("[sidecar] backend ready at {url}");
            }
            Err(err) => eprintln!("[sidecar] malformed READY line: {err}: {rest}"),
        }
    } else {
        eprintln!("[sidecar] {line}");
    }
}

fn main() {
    tauri::Builder::default()
        .manage(SidecarState::default())
        .setup(|app| {
            let child = spawn_sidecar(&app.handle())?;
            let state = app.state::<SidecarState>();
            *state.child.lock().unwrap() = Some(child);
            Ok(())
        })
        .on_window_event(|event| {
            if matches!(event.event(), WindowEvent::Destroyed) {
                let state = event.window().state::<SidecarState>();
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let state = app.state::<SidecarState>();
                if let Some(child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
