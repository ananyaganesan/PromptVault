# Frontend browser smoke and accessibility record

Tested 2026-09-23 against the local Vite prototype using installed Google Chrome. Playwright covers desktop, an iPhone 13-sized viewport, 320px mobile, and 768px tablet widths. This is viewport/device emulation, not a physical iPhone or Safari certification.

| Check | Result |
| --- | --- |
| User login, refresh/session restore, navigation, sign-out | Pass, desktop and mobile |
| Super Admin login and approval route | Pass, desktop and mobile |
| User denied `/admin` | Pass, desktop and mobile |
| Create project, prompt, and new version | Pass, desktop and mobile |
| Registration, duplicate-email conflict, session restore | Pass, desktop and mobile |
| Empty-login validation | Pass, desktop and mobile |
| Top-level user and admin route sweep, no blank page or document overflow | Pass, desktop and mobile |
| Invalid project, prompt, version IDs | Explicit not-found states, desktop and mobile |
| axe-core serious/critical violations on login, dashboard, and all top-level User/Admin screens | None, desktop and mobile |
| Dialog focus entry, focus loop, Escape, restoration | Unit test |
| Reduced-motion handling | CSS media query present |

The route sweep is a smoke test, not full workflow coverage. Automated axe checks do not replace keyboard and screen-reader testing on actual devices. Safari/WebKit, Firefox, and physical small screens remain to be tested before production.

The unit coverage command runs successfully, but current overall statement coverage is about 31%. Browser-level coverage above is supplemental and is not included in that percentage. More unit/integration tests are needed before a production release.

Run from `web/`:

```sh
npm run test:e2e
npm run screenshots
```

See [demo runbook](demo-runbook.md) for the walkthrough. For manual verification, tab through the login form, mobile menu, tables, modal actions, and admin forms; confirm visible focus, readable labels and errors, Escape behavior, no trapped focus outside dialogs, and no page-level horizontal scrolling.
