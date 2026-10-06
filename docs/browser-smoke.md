# Frontend browser smoke and accessibility record

Tested 2026-10-06 against the Docker-backed React, FastAPI, and PostgreSQL stack. Live Playwright tests run serially because they deliberately mutate shared seeded governance and budget data.

| Browser/project | Coverage | Result |
|---|---|---|
| Desktop Chrome | Complete live workflow plus route accessibility sweep | Pass |
| Mobile Chrome, iPhone 13 viewport | Complete live workflow plus route accessibility sweep | Pass |
| Desktop Firefox | Complete live workflow plus route accessibility sweep | Pass |
| Desktop WebKit | Complete live workflow plus route accessibility sweep | Pass |

The workflow suite verifies authentication/session restoration, registration, forbidden-route recovery, project/member/prompt/version persistence, real diff and lineage, run ledger and costs, database budget rejection, staging and production approval, one-time runtime tokens, Serve, rollback, revocation, governance, and maintenance. The route sweep reports no serious or critical axe-core violations and no page-level horizontal overflow on the checked desktop and mobile routes.

Commands run from the repository root:

```bash
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=mobile-chrome
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-firefox
E2E_LIVE=1 npm --prefix web run test:e2e -- --project=desktop-webkit
```

These checks use real Chrome/Chromium, Firefox, and Playwright WebKit engines, with the mobile project using viewport/device emulation rather than a physical iPhone. Automated WebKit coverage improves Safari compatibility confidence but is not physical macOS/iOS Safari certification. Automated axe checks supplement but do not replace manual keyboard, screen-reader, contrast, and physical-device testing.

For manual verification, tab through the login form, mobile navigation, scrollable tables, dialogs, and admin forms; confirm visible focus, readable labels and errors, Escape behavior, focus restoration, and no document-level horizontal scrolling.
