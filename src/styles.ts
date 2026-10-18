export const styles = `
.ddu { display: flex; flex-direction: column; height: var(--ddu-height, calc(100vh - 128px)); min-height: 0; width: 100%; font-size: .875rem; color: var(--gpSystemLightestGrey, #dcdedf); }
.ddu-main { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.ddu * { box-sizing: border-box; }
.ddu [hidden] { display: none !important; }
.ddu-find-input { padding: 0 16px 12px; display: flex; gap: 8px; flex-direction: column; }
.ddu-stars { flex-shrink: 0; white-space: nowrap; font-size: .8rem; line-height: 1.25rem; }
.ddu-toolbar { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; gap: 4px; margin: 0 12px 8px; }
.ddu-icon-button { display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 30px; height: 32px; border-radius: 3px; cursor: pointer; }
.ddu-icon-button[aria-disabled="true"] { opacity: .6; }
.ddu-tabs { display: flex; flex: 1; min-width: 0; gap: 2px; padding: 2px; background: var(--gpBackground-DarkSoft, #171d25); border-radius: 3px; }
.ddu-tab { display: flex; align-items: center; justify-content: center; gap: 4px; flex: 1 1 0; min-width: 0; padding: 7px 4px; text-align: center; font-weight: 500; cursor: pointer; border-radius: 2px; white-space: nowrap; }
.ddu-tab-label { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ddu-tab-count { flex-shrink: 0; }
.ddu-tab[aria-selected="true"] { background: var(--gpBackground-LightMedium, #3d4450); color: var(--gpSystemLightestGrey, #fff); }
.ddu-list { overflow-y: auto; flex: 1; min-height: 0; padding: 2px 8px; overscroll-behavior: contain; }
.ddu-row { display: flex; align-items: flex-start; gap: 10px; width: 100%; min-height: 56px; padding: 8px; border-radius: 2px; cursor: pointer; }
.ddu-plugin-row { display: flex; align-items: stretch; min-width: 0; }
.ddu-plugin-details { flex: 1; min-width: 0; width: auto; }
.ddu-quick-update { flex: 0 0 40px; display: flex; align-items: center; justify-content: center; cursor: pointer; border-radius: 2px; }
.ddu-quick-update[aria-disabled="true"] { opacity: .6; }
.ddu-quick-update:focus-visible { outline: 2px solid #fff; outline-offset: -2px; background: var(--gpBackground-LightMedium, #3d4450); }
.ddu-row-text { flex: 1; min-width: 0; }
.ddu-name, .ddu-subtitle { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; line-height: 1.25rem; }
.ddu-name { font-weight: 500; }
.ddu-subtitle { color: var(--gpSystemLightGrey, #a9b1bc); font-size: .8rem; }
.ddu-status-icon { flex: 0 0 16px; margin-top: 2px; }
.ddu-focused, .ddu-row:focus-visible, .ddu-tab:focus-visible, .ddu-icon-button:focus-visible, .ddu-back:focus-visible { outline: 2px solid var(--gpSystemLightestGrey, #fff); outline-offset: -2px; background: var(--gpBackground-LightMedium, #3d4450); }
.ddu-tab.ddu-focused, .ddu-tab:focus, .ddu-icon-button.ddu-focused, .ddu-icon-button:focus { background: #fff; color: #171d25; outline: 2px solid #fff; }
.ddu-tab[aria-selected="true"] { box-shadow: inset 0 -2px 0 var(--gpColor-Blue, #1a9fff); }
.ddu-empty { padding: 18px 12px; color: var(--gpSystemLightGrey, #a9b1bc); line-height: 1.5; }
.ddu-success-empty { min-height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 9px; padding: 24px 12px 48px; text-align: center; }
.ddu-success-icon { display: flex; align-items: center; justify-content: center; width: 88px; height: 88px; margin-bottom: 8px; border-radius: 50%; color: #79cfa1; background: rgba(91, 183, 132, .13); border: 2px solid rgba(121, 207, 161, .38); font-size: 36px; }
.ddu-success-empty strong { color: var(--gpSystemLightestGrey, #dcdedf); font-size: 1.25rem; font-weight: 600; }
.ddu-success-empty span { color: var(--gpSystemLightGrey, #a9b1bc); font-size: .85rem; line-height: 1.5; }
.ddu-notice { margin: 0 16px 8px; font-size: .8rem; color: var(--gpSystemLightGrey, #a9b1bc); }
.ddu-details { flex: 1; min-height: 0; width: 100%; padding: 0 16px 32px; overflow-y: auto; }
.ddu-back { display: inline-flex; gap: 6px; align-items: center; padding: 8px 4px; margin-bottom: 8px; cursor: pointer; }
.ddu-details h2 { font-size: 1rem; line-height: 1.4; margin: 4px 0 16px; overflow-wrap: anywhere; }
.ddu-versions { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px 14px; margin: 0 0 16px; }
.ddu-versions dt { color: var(--gpSystemLightGrey, #a9b1bc); }
.ddu-versions dd { margin: 0; overflow-wrap: anywhere; text-align: right; }
.ddu-source { margin: 12px 0; overflow-wrap: anywhere; line-height: 1.5; }
.ddu-source-label { display: block; color: var(--gpSystemLightGrey, #a9b1bc); font-size: .8rem; }
.ddu-detail-status { margin: 12px 0; line-height: 1.5; overflow-wrap: anywhere; }
.ddu-actions { display: flex; flex-direction: column; gap: 8px; margin: 16px 0; }
.ddu-actions > * { min-width: 0 !important; width: 100%; font-size: .875rem; padding: 8px 12px; white-space: normal; overflow-wrap: anywhere; }
.ddu-actions > button, .ddu-actions > div > button { width: 100% !important; min-width: 0 !important; }
.ddu-actions > div { width: 100%; }
.ddu-action-label { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; }
.ddu-action-label svg { flex-shrink: 0; }
.ddu-actions .ddu-install-status { margin: 0; padding: 0; line-height: 1.4; color: var(--gpSystemLightGrey, #a9b1bc); }
.ddu-release { display: flex; align-items: center; gap: 12px; padding: 12px; min-height: 48px; margin: 3px 0; border-radius: 3px; background: var(--gpBackground-DarkSoft, #171d25); cursor: pointer; overflow-wrap: anywhere; }
.ddu-release-progress { display: flex; align-items: center; gap: 12px; padding: 12px; margin: 8px 0; border-radius: 4px; background: var(--gpBackground-LightMedium, #3d4450); }
.ddu-release-text { display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 4px; }
.ddu-release-arrow { flex-shrink: 0; width: 12px; height: 12px; }
.ddu-release.ddu-focused, .ddu-release:focus-visible, .ddu-release[aria-disabled="false"]:hover { background: var(--gpBackground-LightMedium, #3d4450); }
.ddu-release small { color: var(--gpSystemLightGrey, #a9b1bc); }
.ddu-release[aria-disabled="true"] { opacity: .65; cursor: default; }
.ddu-candidate { display: flex; flex-direction: column; gap: 6px; }
.ddu-candidate small { color: var(--gpSystemLightGrey, #a9b1bc); line-height: 1.4; }
.ddu-candidate > button { width: 100%; }
.ddu-secondary { opacity: .85; }
.ddu-security-review { box-sizing: border-box; overflow-y: auto; padding: 8px 16px 12px; gap: 8px; line-height: 1.4; overflow-wrap: anywhere; }
.ddu-review-heading { font-size: 1.1rem; font-weight: 600; line-height: 1.4; margin: 0; }
.ddu-review-heading:focus-visible { outline: 2px solid var(--gpSystemLightestGrey, #fff); outline-offset: 2px; }
.ddu-review-heading svg { color: #e4b66a; margin-right: 6px; }
.ddu-security-review p { margin: 8px 0; }
.ddu-security-body { flex: 0 0 auto; overflow: visible; }
.ddu-security-actions { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); flex-shrink: 0; margin: 0; }
.ddu-security-actions > div { padding: 0; }
.ddu-security-checkbox { display: flex; align-items: flex-start; gap: 8px; padding: 8px 4px; cursor: pointer; }
.ddu-security-checkbox .DialogCheckbox { flex-shrink: 0; border: 2px solid #c7d5e0; background: #171d25; box-shadow: none; }
.ddu-security-checkbox .DialogCheckbox.Active { background: #66c0f4; border-color: #66c0f4; color: #171d25; }
.ddu-security-checkbox:focus, .ddu-security-checkbox:focus-within, .ddu-security-checkbox.gpfocus, .ddu-security-checkbox.gpfocuswithin { outline: 2px solid #fff; outline-offset: -2px; background: #3d4450; color: #fff; }
.ddu-security-checkbox .DialogToggle_Label { color: inherit; }
.ddu-security-checkbox svg { flex-shrink: 0; }
.ddu-capability-explanation { padding: 0 4px 4px 28px; overflow-wrap: anywhere; }
.ddu-capability-explanation p { margin: 4px 0 8px; }
.ddu-capabilities-title { display: block; margin-bottom: 8px; }
.ddu-capabilities-note { display: block; margin: 10px 0 0; line-height: 1.4; color: var(--gpSystemLightGrey, #b8bcbf); }
.ddu-capabilities { margin: 8px 0; overflow-wrap: anywhere; }
.ddu-capability-row { display: flex; align-items: center; gap: 8px; padding: 7px 4px; min-height: 30px; cursor: pointer; }
.ddu-capability-row svg { width: 16px; height: 16px; flex-shrink: 0; }
.ddu-capability-row span { flex: 1; }
.ddu-capability-evidence { margin: 4px 0; padding-left: 24px; }
.ddu-capability-evidence li { margin-bottom: 6px; }
.ddu-security-details { margin: 8px 0; overflow-wrap: anywhere; }
.ddu-security-disclosure { display: flex; align-items: center; gap: 8px; min-height: 36px; padding: 8px 4px; cursor: pointer; border-top: 1px solid rgba(169,177,188,.2); }
.ddu-security-disclosure svg { flex-shrink: 0; width: 10px; height: 10px; }
.ddu-disclosure-open { transform: rotate(90deg); }
.ddu-security-binary { display: flex; flex-direction: column; gap: 4px; margin: 10px 0; }
.ddu-security-summary { margin: 8px 0; padding-left: 20px; line-height: 1.45; }
.ddu-security-summary > li { margin: 7px 0; }
.ddu-actions > button.ddu-uninstall { background: transparent; color: var(--gpSystemLightGrey, #a9b1bc); box-shadow: none; }
.ddu-actions > button.ddu-uninstall:focus-visible, .ddu-actions > button.ddu-uninstall:focus { outline: 2px solid var(--gpSystemLightestGrey, #fff); outline-offset: -2px; background: var(--gpBackground-LightMedium, #3d4450); }
.ddu-footnote { color: var(--gpSystemLightGrey, #a9b1bc); font-size: .75rem; line-height: 1.4; margin-top: 16px; }
`;
