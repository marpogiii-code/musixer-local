module.exports = {
  run: [
    // ACE-Step 1.5 (music engine) in its own uv-managed environment
    { method: "shell.run", params: { message: "git clone https://github.com/ace-step/ACE-Step-1.5 app/ACE-Step-1.5 || git -C app/ACE-Step-1.5 pull" } },
    { method: "shell.run", params: { path: "app/ACE-Step-1.5", message: "uv sync" } },
    // Musixer web app + Kokoro TTS + Demucs
    { method: "script.start", params: { uri: "torch.js", params: { venv: "env", path: "." } } },
    { method: "shell.run", params: { venv: "env", message: "uv pip install -r requirements.txt" } },
    { when: "{{platform === 'linux'}}", method: "shell.run", params: { message: "(command -v espeak-ng || sudo apt-get install -y espeak-ng || true)" } },
    { when: "{{platform === 'darwin'}}", method: "shell.run", params: { message: "(command -v espeak-ng || brew install espeak-ng || true)" } },
    { method: "notify", params: { html: "Installed. Click Start (ACE-Step downloads its models on first launch)." } },
  ],
}
