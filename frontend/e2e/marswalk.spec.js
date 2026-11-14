// Requires Playwright and a running Vite/backend pair. Not run here: dependencies unavailable.
import {test,expect} from '@playwright/test';
const BASE=process.env.MARSWALK_UI??'http://localhost:5175';
async function simulation(page){
  await page.goto(BASE);
  await page.getByRole('button',{name:'Generate mission route',exact:true}).click();
  await expect(page.locator('.verdict')).toHaveText(/GO|CAUTION|NO-GO/);
  await page.getByRole('button',{name:'Open simulation',exact:true}).click();
  await expect(page.getByLabel('Simulation controls')).toBeVisible();
}
test('planning keeps operations separate and floats the map on scroll',async({page})=>{
  await page.goto(BASE);
  await expect(page.getByRole('heading',{name:'Plan the next expedition.'})).toBeVisible();
  await expect(page.getByLabel('Simulation controls')).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Reference',exact:true})).toHaveCount(0);
  await page.getByRole('heading',{name:'Design the excursion.'}).scrollIntoViewIfNeeded();
  await expect(page.locator('.planning-map')).toHaveClass(/is-pip/);
  await page.getByRole('button',{name:'Return to full map'}).click();
  await expect(page.locator('.planning-map')).not.toHaveClass(/is-pip/);
});
test('tracker steps and reset share the map position',async({page})=>{
  await simulation(page);
  await expect(page.getByLabel('Astronaut first-person tracker')).toBeVisible();
  await expect(page.getByLabel('EVA watch with habitat and route compasses')).toBeVisible();
  const position=page.locator('.shared-position-row'),initial=await position.innerText();
  await page.getByRole('button',{name:'Preview forward 100 meters',exact:true}).click();
  await expect(position).not.toHaveText(initial);
  await expect(page.getByRole('slider',{name:'Shared route progress'})).not.toHaveValue('0');
  await page.getByRole('button',{name:'Reset shared navigation',exact:true}).click();
  await expect(position).toHaveText(initial);
  await page.getByRole('button',{name:'Sensor details',exact:true}).click();
  await expect(page.getByRole('heading',{name:'A closer look at every system.'})).toBeVisible();
});
test('live control locks preview stepping and shows telemetry',async({page})=>{
  await simulation(page);
  await page.getByRole('button',{name:'Start EVA',exact:true}).click();
  await expect(page.getByRole('button',{name:'Pause EVA',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Preview forward 100 meters',exact:true})).toBeDisabled();
  await expect(page.getByRole('heading',{name:'Astronaut & environment'})).toHaveCount(1);
  await page.getByRole('button',{name:'Pause EVA',exact:true}).click();
  await page.getByRole('button',{name:'Route preview',exact:true}).click();
  await expect(page.getByRole('button',{name:'Preview forward 100 meters',exact:true})).toBeEnabled();
});
test('unavailable backend keeps explicit demo data',async({page})=>{
  await page.route('**/api/**',route=>route.abort());await page.goto(BASE);
  await expect(page.getByText('DEMONSTRATION DATA',{exact:true})).toBeVisible();
});
