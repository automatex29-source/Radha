/** Open Settings from anywhere (the profile menu, an upgrade hint, the OAuth return) at a given section. */
export const OPEN_SETTINGS_EVENT = "krish:open-settings";

export function openSettings(section = null) {
  window.dispatchEvent(new CustomEvent(OPEN_SETTINGS_EVENT, { detail: section }));
}
