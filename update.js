module.exports = {
  run: [
    { method: "shell.run", params: { message: "git pull" } },
    { method: "shell.run", params: { path: "app/ACE-Step-1.5", message: ["git pull", "uv sync"] } },
    { method: "shell.run", params: { venv: "env", message: "uv pip install -r requirements.txt" } },
  ],
}
