// Google's own file picker, for the Drive and Sheets connectors. Krish asks Google only for the files the user picks
// here (the drive.file permission), so Google shows no "unverified app" warning for these two apps.
let loading = null;

function loadPicker() {
  if (window.google?.picker) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const done = () => window.gapi.load("picker", { callback: resolve, onerror: reject });
      if (window.gapi) { done(); return; }
      const s = document.createElement("script");
      s.src = "https://apis.google.com/js/api.js";
      s.async = true;
      s.onload = done;
      s.onerror = () => { loading = null; reject(new Error("Couldn't load Google's file picker. Check your internet.")); };
      document.head.appendChild(s);
    });
  }
  return loading;
}

/** Open the picker. `setup` is the /connectors/{id}/picker answer. Resolves with the picked files ([] if closed). */
export async function pickGoogleFiles(setup) {
  await loadPicker();
  const P = window.google.picker;
  const view = setup.view === "sheets"
    ? new P.DocsView(P.ViewId.SPREADSHEETS).setMode(P.DocsViewMode.LIST)
    : new P.DocsView(P.ViewId.DOCS).setIncludeFolders(true).setMode(P.DocsViewMode.LIST);
  return new Promise((resolve) => {
    const builder = new P.PickerBuilder()
      .addView(view)
      .enableFeature(P.Feature.MULTISELECT_ENABLED)
      .enableFeature(P.Feature.SUPPORT_DRIVES)
      .setOAuthToken(setup.token)
      .setAppId(setup.appId)
      .setOrigin(window.location.origin)
      .setTitle(setup.view === "sheets" ? "Choose the sheets Krish may use" : "Choose the files Krish may read")
      .setCallback((data) => {
        const action = data[P.Response.ACTION];
        if (action === P.Action.PICKED) resolve((data[P.Response.DOCUMENTS] || []).map((d) => ({ id: d[P.Document.ID], name: d[P.Document.NAME] })));
        else if (action === P.Action.CANCEL) resolve([]);
      });
    if (setup.apiKey) builder.setDeveloperKey(setup.apiKey);
    builder.build().setVisible(true);
  });
}
