// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::Manager;

struct BackendProcess(Mutex<Option<std::process::Child>>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            // In debug/dev mode there is no bundled sidecar binary —
            // rely on the manually-started FastAPI backend instead.
            #[cfg(not(debug_assertions))]
            {
                // Kill any stale backend process from a previous version/session.
                // On Windows, kill by name (reliable) then give the OS a moment to
                // release the port before we try to bind it again.
                #[cfg(target_os = "windows")]
                {
                    let _ = std::process::Command::new("taskkill")
                        .args(["/F", "/IM", "backend.exe"])
                        .output(); // output() waits for taskkill to finish
                    std::thread::sleep(std::time::Duration::from_millis(500));
                }
                #[cfg(not(target_os = "windows"))]
                let _ = std::process::Command::new("sh")
                    .args(["-c", "lsof -ti:8001 | xargs kill -9 2>/dev/null || true"])
                    .status();

                // Resolve log path
                let log_dir = app.path().app_log_dir()
                    .unwrap_or_else(|_| std::path::PathBuf::from("/tmp"));
                let _ = std::fs::create_dir_all(&log_dir);
                let log_path = log_dir.join("backend.log");

                eprintln!("[tauri] Backend log → {}", log_path.display());

                // Resolve the onedir backend binary from Resources
                let resource_dir = app.path().resource_dir()
                    .expect("resource dir not found");
                // Tauri copies resources/backend/**/* preserving the path relative to src-tauri,
                // so the binary ends up at Contents/Resources/resources/backend/backend
                #[cfg(target_os = "windows")]
                let backend_bin = resource_dir.join("resources").join("backend").join("backend.exe");
                #[cfg(not(target_os = "windows"))]
                let backend_bin = resource_dir.join("resources").join("backend").join("backend");

                eprintln!("[tauri] Launching backend: {}", backend_bin.display());

                #[cfg(target_os = "windows")]
                use std::os::windows::process::CommandExt;

                let mut cmd = std::process::Command::new(&backend_bin);
                // The backend reports this in /api/health; the start screen compares it with the app's own
                // version, so a backend left over from an older version is noticed.
                cmd.env("ULTRASTAR_APP_VERSION", app.package_info().version.to_string());
                cmd.stdout(std::process::Stdio::piped())
                   .stderr(std::process::Stdio::piped());
                #[cfg(target_os = "windows")]
                cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW — suppress console popup
                let mut child = cmd.spawn()
                    .expect("Failed to spawn backend process");

                // Stream stdout+stderr to log file in background thread
                let stdout = child.stdout.take();
                let stderr = child.stderr.take();
                let log_path_clone = log_path.clone();

                std::thread::spawn(move || {
                    use std::io::{BufRead, BufReader, Write};
                    let mut log_file = std::fs::OpenOptions::new()
                        .create(true).append(true).open(&log_path_clone)
                        .ok();

                    if let Some(ref mut f) = log_file {
                        let ts = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_secs()).unwrap_or(0);
                        let _ = writeln!(f, "\n--- sidecar start (t={ts}) ---");
                    }

                    // Merge stdout and stderr via a simple approach: read stderr on another thread
                    if let Some(err) = stderr {
                        let log_path_err = log_path_clone.clone();
                        std::thread::spawn(move || {
                            let mut log_err = std::fs::OpenOptions::new()
                                .create(true).append(true).open(&log_path_err)
                                .ok();
                            for line in BufReader::new(err).lines().map_while(Result::ok) {
                                eprint!("[backend] {}\n", line);
                                if let Some(ref mut f) = log_err {
                                    let _ = writeln!(f, "{}", line);
                                    let _ = f.flush();
                                }
                            }
                        });
                    }

                    if let Some(out) = stdout {
                        for line in BufReader::new(out).lines().map_while(Result::ok) {
                            eprint!("[backend] {}\n", line);
                            if let Some(ref mut f) = log_file {
                                let _ = writeln!(f, "{}", line);
                                let _ = f.flush();
                            }
                        }
                    }
                });

                *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Kill the managed backend child process
                if let Ok(mut guard) = window.app_handle().state::<BackendProcess>().0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait(); // reap zombie so OS fully releases the port
                    }
                }
                // Belt-and-suspenders: taskkill by name covers the case where Drop
                // didn't run (e.g. force-killed by an installer update).
                #[cfg(target_os = "windows")]
                let _ = std::process::Command::new("taskkill")
                    .args(["/F", "/IM", "backend.exe"])
                    .output();
                #[cfg(not(target_os = "windows"))]
                let _ = std::process::Command::new("sh")
                    .args(["-c", "lsof -ti:8001 | xargs kill -9 2>/dev/null || true"])
                    .status();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

