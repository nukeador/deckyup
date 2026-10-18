// Browser-only fixture. Excluded from production allowlist packaging.
import { createRoot } from "react-dom/client";
import { LanguageProvider } from "../../src/i18n";
import { SecurityReviewBoundary } from "../../src/SecurityReview";
import {
  createSecurityInstaller,
  type SecurityAssessment,
} from "../../src/securityInstaller";
const language = new URLSearchParams(location.search).get("lang") || "english";
Object.assign(window, {
  SteamClient: { Settings: { GetCurrentLanguage: async () => language } },
});
const updating = new URLSearchParams(location.search).has("update");
const security: SecurityAssessment = {
  root_requested: true,
  previous_root_requested: updating ? false : null,
  flags: ["root"],
  has_python_backend: true,
  previous_has_python_backend: false,
  external_binaries: [
    {
      name: "example-helper",
      source_host: "downloads.example.org",
      declared_hash: "a".repeat(64),
    },
  ],
  previous_external_binaries: [],
  added_binary_names: ["example-helper"],
  changed_binary_source_hosts: [],
  comparison_available: updating,
  updating,
  requires_acknowledgment: true,
  findings: [
    { kind: updating ? "root_added" : "root_requested", severity: "warning" },
    { kind: "external_binaries_added", severity: "warning" },
  ],
};
const staged = {
  artifact: "file:///tmp/staged/update-preview.zip",
  name: "Example Plugin",
  version: "1.4.0",
  previous_version: updating ? "1.3.0" : undefined,
  hash: "a".repeat(64),
  review_token: "preview",
  security,
};
const installer = createSecurityInstaller({
  authorize: async () => ({
    update: { ...staged, security_authorized: true },
    error: null,
  }),
  discard: async () => {},
  request: async () => {
    document.getElementById("result")!.textContent =
      "Mock native confirmation requested";
    return { requested: true };
  },
});
createRoot(document.getElementById("root")!).render(
  <LanguageProvider>
    <SecurityReviewBoundary installer={installer}>
      <div className="ddu">
        <button onClick={() => void installer.request(staged)}>
          Install preview
        </button>
        <p id="result">Development preview · no installation</p>
      </div>
    </SecurityReviewBoundary>
  </LanguageProvider>,
);
