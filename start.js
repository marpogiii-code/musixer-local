module.exports = {
  daemon: true,
  run: [
    {
      when: "{{!(args && args.mock)}}",
      method: "shell.run",
      params: {
        path: "app/ACE-Step-1.5",
        env: { ACESTEP_API_HOST: "127.0.0.1", ACESTEP_API_PORT: "8001", ACESTEP_OFFLOAD_TO_CPU: "{{gpu === 'nvidia' ? 'false' : 'true'}}" },
        message: "uv run acestep-api",
        on: [{ event: "/Uvicorn running on|Application startup complete/i", done: true }],
      },
    },
    {
      method: "shell.run",
      params: {
        venv: "env",
        env: { MUSIXER_PORT: "{{port}}", MUSIXER_MUSIC_ENGINE: "{{args && args.mock ? 'mock' : 'acestep'}}", ACESTEP_URL: "http://127.0.0.1:8001" },
        message: "python -m musixer",
        on: [{ event: "/http:\\/\\/[0-9.:]+/", done: true }],
      },
    },
    { method: "local.set", params: { url: "{{input.event[0]}}" } },
  ],
}
