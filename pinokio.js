const path = require("path")
module.exports = {
  version: "3.7",
  title: "Musixer Local",
  description: "Local AI music studio: songs with vocals (ACE-Step 1.5), covers, repaint, extend, stems, AI speech, lyric studio. No login, no credits.",
  icon: "icon.png",
  menu: async (kernel, info) => {
    const installed = info.exists("env") && info.exists("app/ACE-Step-1.5/.venv")
    const running = {
      install: info.running("install.js"),
      start: info.running("start.js"),
      update: info.running("update.js"),
      reset: info.running("reset.js"),
    }
    if (running.install) return [{ default: true, icon: "fa-solid fa-plug", text: "Installing", href: "install.js" }]
    if (!installed) return [{ default: true, icon: "fa-solid fa-plug", text: "Install", href: "install.js" }]
    if (running.start) {
      const local = info.local("start.js")
      const items = []
      if (local && local.url) items.push({ default: true, icon: "fa-solid fa-music", text: "Open Musixer", href: local.url })
      items.push({ icon: "fa-solid fa-terminal", text: "Terminal", href: "start.js" })
      return items
    }
    if (running.update) return [{ default: true, icon: "fa-solid fa-terminal", text: "Updating", href: "update.js" }]
    if (running.reset) return [{ default: true, icon: "fa-solid fa-terminal", text: "Resetting", href: "reset.js" }]
    return [
      { default: true, icon: "fa-solid fa-power-off", text: "Start", href: "start.js" },
      { icon: "fa-solid fa-flask", text: "Start (demo synth, no GPU)", href: "start.js", params: { mock: true } },
      { icon: "fa-solid fa-rotate", text: "Update", href: "update.js" },
      { icon: "fa-solid fa-plug", text: "Reinstall", href: "install.js" },
      { icon: "fa-regular fa-circle-xmark", text: "Reset", href: "reset.js", confirm: "Remove the environments (your library in data/ is kept)?" },
    ]
  },
}
