# Project Checklist

- [x] Verify that the copilot-instructions.md file in the .github directory is created.

- [x] Clarify Project Requirements
	<!-- Project details provided: AI-Powered Ultrastar Song Generator with Svelte frontend (Vite), Python FastAPI backend, local AI models for audio processing. -->

- [x] Scaffold the Project
	<!-- Svelte frontend scaffolded with Vite. Python backend folder created with requirements.txt and main.py. Dependencies installed. -->

- [x] Customize the Project
	<!-- Basic Svelte app created with upload placeholder. -->

- [x] Install Required Extensions
	<!-- No extensions needed for Vite or Python projects. -->

- [x] Compile the Project
	<!-- Dependencies installed. Vulnerabilities fixed. Python imports tested successfully. -->

- [x] Create and Run Task
	<!-- Tasks created for starting frontend and backend servers. -->

- [x] Launch the Project
	<!-- Frontend and backend servers started in background. -->

- [x] Ensure Documentation is Complete
	<!-- README.md created and up to date. -->

## TODO Later

- [ ] **Lyrics comparison in Step 2**: Before generating, compare user-pasted lyrics against what MFA actually hears in the audio. Show warnings for mismatched/phantom words (extra articles, missing words, etc.) so the user can fix lyrics before alignment runs.
- [ ] **Golden note editing**: Support `*` (golden notes) in the piano roll editor.
- [ ] **Tied/continuation notes**: Support `~` (tied notes) in the piano roll editor.
- [ ] **Audio waveform display**: Show waveform visualization on top or bottom of the piano roll.
- [ ] **MIDI/pitch tone playback toggle**: On/off switch to play a synthesized tone following the pitch during playback.
- [ ] **MIDI/pitch tone volume**: Volume slider for the synthesized pitch tone.
- [ ] **Play selected note tone**: Add a button in the note info panel (top right) to play the pitch of the currently selected note.

## Execution Guidelines
PROGRESS TRACKING:
- If any tools are available to manage the above todo list, use it to track progress through this checklist.
- After completing each step, mark it complete and add a summary.
- Read current todo list status before starting each new step.

COMMUNICATION RULES:
- Avoid verbose explanations or printing full command outputs.
- If a step is skipped, state that briefly (e.g. "No extensions needed").
- Do not explain project structure unless asked.
- Keep explanations concise and focused.

DEVELOPMENT RULES:
- Use '.' as the working directory unless user specifies otherwise.
- Avoid adding media or external links unless explicitly requested.
- Use placeholders only with a note that they should be replaced.
- Use VS Code API tool only for VS Code extension projects.
- Once the project is created, it is already opened in Visual Studio Code—do not suggest commands to open this project in vscode.
- If the project setup information has additional rules, follow them strictly.

FOLDER CREATION RULES:
- Always use the current directory as the project root.
- If you are running any terminal commands, use the '.' argument to ensure that the current working directory is used ALWAYS.
- Do not create a new folder unless the user explicitly requests it besides a .vscode folder for a tasks.json file.
- If any of the scaffolding commands mention that the folder name is not correct, let the user know to create a new folder with the correct name and then reopen it again in vscode.

EXTENSION INSTALLATION RULES:
- Only install extension specified by the get_project_setup_info tool. DO NOT INSTALL any other extensions.

PROJECT CONTENT RULES:
- If the user has not specified project details, assume they want a "Hello World" project as a starting point.
- Avoid adding links of any type (URLs, files, folders, etc.) or integrations that are not explicitly required.
- Avoid generating images, videos, or any other media files unless explicitly requested.
- If you need to use any media assets as placeholders, let the user know that these are placeholders and should be replaced with the actual assets later.
- Ensure all generated components serve a clear purpose within the user's requested workflow.
- If a feature is assumed but not confirmed, prompt the user for clarification before including it.
- If you are working on a VS Code extension, use the VS Code API tool with a query to find relevant VS Code API references and samples related to that query.

TASK COMPLETION RULES:
- Your task is complete when:
  - Project is successfully scaffolded and compiled without errors
  - copilot-instructions.md file in the .github directory exists in the project
  - README.md file exists and is up to date
  - User is provided with clear instructions to debug/launch the project

Before starting a new task in the above plan, update progress in the plan.