// Audit: specificații Playwright pentru frontend. NERULATE în audit (instalarea Playwright și a
// browserului cere rețea; package.json e înghețat). Comanda exactă e în docs/audit/RAPORT_AUDIT.md.
//
// Presupun: Vite pe http://localhost:5175 cu BACKEND_URL=http://127.0.0.1:8002, backend pe 8002.
// Textele căutate sunt cele din frontend/src la commitul auditat (UI parțial în engleză, vezi AUDIT-012).
import { test, expect } from '@playwright/test';

const BASE = process.env.MARSWALK_UI ?? 'http://localhost:5175';

test.describe('Marswalk UI', () => {
  test('încărcarea hărții: ecranul principal apare, nu rămâne pe „Loading”', async ({ page }) => {
    await page.goto(BASE);
    await expect(page.getByText('Loading expedition area...')).toHaveCount(0, { timeout: 15000 });
    await expect(page.getByLabel('Simulation controls')).toBeVisible();
  });

  test('selectarea unei ținte și planificarea: traseul și verdictul apar', async ({ page }) => {
    await page.goto(BASE);
    await page.getByRole('button', { name: /Plan EVA|Edit EVA plan/ }).click();
    await page.getByRole('checkbox').first().check();
    await page.getByRole('button', { name: /Genereaz|Generate/ }).click();
    await expect(page.locator('.verdict')).toHaveText(/GO|CAUTION|NO-GO/, { timeout: 15000 });
  });

  test('pornirea live: apare o decizie și explicația ei', async ({ page }) => {
    await page.goto(BASE);
    await page.getByRole('button', { name: /Plan EVA/ }).click();
    await page.getByRole('checkbox').first().check();
    await page.getByRole('button', { name: /Genereaz|Generate/ }).click();
    await page.getByRole('button', { name: 'Start EVA' }).click();
    await page.getByLabel('Simulation speed').selectOption('60');
    // Scena demo: primul pericol programat la minutul 30 (scenario.demo_events).
    await expect(page.locator('.decision-title')).toHaveText(/REROUTE|ocolire|detour|Return|Urgen|Emergency/i, { timeout: 30000 });
    await expect(page.locator('.source-label')).toBeVisible({ timeout: 15000 });
  });

  test('backend oprit: mesaj de eroare sau mod demonstrativ, nu ecran gol', async ({ page }) => {
    await page.route('**/api/**', route => route.abort());
    await page.goto(BASE);
    await expect(page.locator('body')).not.toBeEmpty();
    await expect(page.getByText(/DEMONSTRATION DATA|Recorded scenario|Live link interrupted/)).toBeVisible({ timeout: 15000 });
  });

  test('reconectare: după întreruperea WebSocket apare bannerul, apoi dispare', async ({ page, context }) => {
    await page.goto(BASE);
    await page.getByRole('button', { name: /Plan EVA/ }).click();
    await page.getByRole('checkbox').first().check();
    await page.getByRole('button', { name: /Genereaz|Generate/ }).click();
    await page.getByRole('button', { name: 'Start EVA' }).click();
    await context.setOffline(true);
    await expect(page.getByText('Live link interrupted. Last received data retained; position is held.')).toBeVisible({ timeout: 20000 });
    await context.setOffline(false);
    await expect(page.getByText('Live link interrupted. Last received data retained; position is held.')).toHaveCount(0, { timeout: 30000 });
  });
});
