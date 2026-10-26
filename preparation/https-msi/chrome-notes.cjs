'use strict';
const fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.WAVY_PLAYWRIGHT_CORE);
const {diagnostics}=require('./chrome-diagnostics.cjs');
const origin='https://recettelocal.wavyservices.fr';
async function main(){
 if(process.argv.includes('--layout'))return layout();
 if(process.argv.includes("--preview")||process.argv.includes("--permanent")) return preview();
 const [input,dir]=process.argv.slice(2),f=JSON.parse(fs.readFileSync(input,'utf8'));
 const result={passed:false,noteIds:[],requests:0,fileVersions:0,checks:[]};
 const diag=diagnostics(dir,[f.cookie,f.cookie?.split('=')[1]]);
 const save=()=>fs.writeFileSync(path.join(dir,'chrome-notes-results.json'),JSON.stringify(result,null,2));
 function check(label,ok){result.checks.push({control:label,passed:!!ok});save();if(!ok)throw new Error('CHECK_FAILED');}
 let b,p;
 try{
  diag.stage('launch-Chrome');b=await chromium.launch({channel:'chrome',headless:false});diag.result.browser=b.version();
  const c=await b.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  diag.attach(c);
  await c.addCookies([{name:'WAVY_SESSION',value:f.cookie.split('=')[1],domain:'recettelocal.wavyservices.fr',path:'/',secure:true,httpOnly:true,sameSite:'Strict'}]);
  await c.route('**/*',async route=>{
   const r=route.request(),u=new URL(r.url());result.requests++;
   const writable=(r.method()==='POST'&&u.pathname==='/api/notes-frais'&&result.noteIds.length===0)||
    (r.method()==='PUT'&&result.noteIds.length===1&&u.pathname==='/api/notes-frais/'+result.noteIds[0]);
   if(result.requests>150||(!['data:','blob:'].includes(u.protocol)&&u.origin!==origin)||(!['GET','HEAD','OPTIONS'].includes(r.method())&&!writable)){diag.blocked(r);return route.abort('blockedbyclient');}
   return route.continue();
  });
  p=await c.newPage();diag.stage('open-PWA-manual-form');await diag.navigation(await p.goto(origin+'/pwa/notes-frais/carte-entreprise/nouveau?mode=manuel'));
  diag.stage('locate-PWA-heading');
  await p.getByRole('heading',{name:'Nouvelle dépense carte entreprise'}).waitFor();
  diag.stage('locate-beneficiary');await p.locator('input[name="personneConcernee"]').waitFor();
  diag.stage('fill-PWA-form');
  await p.locator('input[type="file"]').last().setInputFiles(f.file);
  await p.locator('input[name="dateDepense"]').fill('2026-10-25');
  await p.locator('input[name="libelle"]').fill(f.label);
  await p.locator('input[name="montantHt"]').fill('30');
  await p.locator('input[name="montantTva"]').fill('6');
  const creating=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/notes-frais'&&r.request().method()==='POST');
  diag.stage('create-note');result.fileVersions++;save();await p.getByRole('button',{name:'Créer note de frais',exact:true}).click();
  const created=await creating;check('PWA-create-real-multipart',created.status()===200);
  const note=await created.json();result.noteIds.push(note.id);save();check('PWA-created-own-company',note.tenantId===f.tenant&&note.societeInterneId===f.company);
  await p.getByText(f.label,{exact:true}).waitFor();check('PWA-list-created-note',true);
  diag.stage('open-note-detail');await p.getByText(f.label,{exact:true}).click();await p.getByRole('link',{name:'Modifier',exact:true}).waitFor();
  await p.screenshot({path:path.join(dir,'note-detail.png')});check('PWA-detail-visible',true);
  diag.stage('edit-note');await p.getByRole('link',{name:'Modifier',exact:true}).click();
  await p.locator('input[name="libelle"]').fill(f.label+' MODIFIEE');
  await p.locator('input[type="file"]').last().setInputFiles(f.file);
  const modifying=p.waitForResponse(r=>new URL(r.url()).pathname==='/api/notes-frais/'+note.id&&r.request().method()==='PUT');
  result.fileVersions++;save();await p.getByRole('button',{name:'Enregistrer la note de frais',exact:true}).click();
  check('PWA-modify-real-multipart',(await modifying).status()===200);
  await p.getByText(f.label+' MODIFIEE',{exact:true}).waitFor();check('PWA-list-modified-note',true);
  await p.screenshot({path:path.join(dir,'note-modified.png')});result.passed=true;save();diag.stage('completed');await diag.finish(p);await c.close();
 }catch(error){await diag.finish(p,error);throw error;}
 finally{save();if(b)await b.close();}
}
async function preview(){
 const [input,dir]=process.argv.slice(2),f=JSON.parse(fs.readFileSync(input,'utf8'));
 const permanent=process.argv.includes('--permanent');
 const result={passed:false,checks:[],businessWrites:0,tlsVerified:true,mockedResponses:false};
 const diag=diagnostics(dir,[f.Email,f['Mot de passe']]);
 const save=()=>fs.writeFileSync(path.join(dir,'pwa-preview-results.json'),JSON.stringify(result,null,2));
 const check=(control,passed)=>{result.checks.push({control,passed:!!passed});save();if(!passed)throw Error('PREVIEW_CHECK_FAILED');};
 let browser,page,ready=false;
 try{
  browser=await chromium.launch({channel:'chrome',headless:false});diag.result.browser=browser.version();
  const c=await browser.newContext({ignoreHTTPSErrors:false,serviceWorkers:permanent?'allow':'block'});diag.attach(c);
  await c.route('**/*',async route=>{
   const r=route.request(),u=new URL(r.url());
   if((!['data:','blob:'].includes(u.protocol)&&u.origin!==origin)||(!['GET','HEAD','OPTIONS'].includes(r.method())&&!permanent&&!(r.method()==='POST'&&u.pathname==='/api/auth/session'))){diag.blocked(r);return route.abort('blockedbyclient');}
   return route.continue();
  });
  page=await c.newPage();diag.stage('preview-login');await diag.navigation(await page.goto(origin));
  await page.getByLabel('Adresse email').fill(f.Email);await page.getByLabel('Mot de passe').fill(f['Mot de passe']);
  const login=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/auth/session'&&r.request().method()==='POST');
  await page.getByRole('button',{name:'Se connecter',exact:true}).click();check('real-login', (await login).status()===200);
  await page.getByRole('heading',{name:/Bonjour/}).waitFor();
  const read=async(p,url)=>p.evaluate(async url=>{const r=await fetch(url,{credentials:'same-origin',cache:'no-store'});return {status:r.status,text:await r.text()};},url);
  const session=await read(page,'/api/auth/session');check('live-Socle-session',session.status===200);const profile=JSON.parse(session.text);
  const cookie=(await c.cookies()).find(v=>v.name==='WAVY_SESSION');check('secure-httpOnly-strict-cookie',cookie?.secure&&cookie?.httpOnly&&cookie?.sameSite==='Strict');
  check('account-context',profile.utilisateurId===2&&profile.tenantId===3&&[4,5].includes(profile.societeCouranteId));
  check('role',profile.roles?.some(r=>['NOTE_DE_FRAIS','SUPER_NOTE_DE_FRAIS'].includes(r)));
  // Cookie is sent once through the private anonymous parent pipe, never saved/logged.
  if(!permanent){ process.stdout.write(JSON.stringify({kind:'session',cookie:'WAVY_SESSION='+cookie.value,user:profile.utilisateurId,tenant:profile.tenantId,company:profile.societeCouranteId,roles:profile.roles})+'\n');
  await new Promise((resolve,reject)=>{process.stdin.once('data',v=>v.toString().trim()==='open'?resolve():reject(Error('GATE_ACK')));}); }
  diag.stage('preview-gated-dashboard');if(!permanent)await page.reload();
  await page.getByRole('heading',{name:/Bonjour/}).waitFor();
  const manifest=await read(page,'/pwa-integration.json');check('manifest-session-enabled',manifest.status===200&&JSON.parse(manifest.text).enabled===true);
  const link=permanent?page.locator('.sidebar').getByRole('button',{name:'Mobile PWA',exact:true}):page.getByRole('link',{name:'Wavy PWA',exact:true});await link.waitFor();check('ERP-authorized-link',true);
  const other=await browser.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  const otherPage=await other.newPage();await otherPage.goto(origin);
  check('anonymous-PWA-denied',(await read(otherPage,'/pwa/')).status===404);
  check(permanent?'public-module-availability-only':'anonymous-manifest-disabled',JSON.parse((await read(otherPage,'/pwa-integration.json')).text).enabled===permanent);
  // A different session value cannot reuse the lease, even when its name is valid.
  await other.addCookies([{name:'WAVY_SESSION',value:'unapproved-preview-session',domain:'recettelocal.wavyservices.fr',path:'/',secure:true,httpOnly:true}]);
  check('foreign-session-denied',(await read(otherPage,'/pwa/')).status===404);await other.close();
  const notes=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/notes-frais'&&r.request().method()==='GET');
  diag.stage('preview-PWA-list');await link.click();
  if(permanent){
   await page.waitForURL(/module=pwa/);const iframe=page.locator('iframe[title="Module Wavy"]');
   await iframe.waitFor();check('PWA-embedded-same-application',(await iframe.getAttribute('src'))==='/pwa/notes-frais');
   check('PWA-list-API',(await notes).status()===200);
   const frame=page.frameLocator('iframe[title="Module Wavy"]');await frame.locator('h1').waitFor();
   check('ERP-sidebar-preserved',await page.locator('.sidebar').isVisible());
   check('camera-permission-in-frame',await iframe.evaluate(el=>el.contentDocument.featurePolicy.allowsFeature('camera')));
   check('no-nested-ERP-link',await frame.getByRole('link',{name:'Retour à Wavy ERP'}).count()===0);
   await frame.getByRole('link',{name:'Profil',exact:true}).last().click();
   await page.waitForURL(u=>u.searchParams.get('module')==='pwa'&&u.searchParams.get('path')==='/profil');
   check('internal-PWA-route-synchronized',true);
   await page.reload();await page.frameLocator('iframe[title="Module Wavy"]').getByLabel('Société courante').waitFor();check('embedded-deep-link-reload',true);
   // Reuse the canonical session when the company is changed from the Shell.
   const select=page.locator('header select');const original=await select.inputValue();
   const companies=await select.locator('option').evaluateAll(options=>options.map(o=>o.value));
   const alternate=companies.find(id=>id!==original);
   if(alternate){await select.selectOption(alternate);
    await page.waitForFunction(id=>{const f=document.querySelector('iframe');const data=f?.contentWindow?.localStorage.getItem('wavy-pwa-contexte');return data&&JSON.parse(data).societeCouranteId===Number(id);},alternate);
    check('Shell-company-reloads-PWA-context',true);
    await page.frameLocator('iframe[title="Module Wavy"]').getByLabel('Société courante').selectOption({label:await select.locator('option[value="'+original+'"]').innerText()});
    await page.waitForFunction(id=>document.querySelector('header select')?.value===id,original);
    check('PWA-company-synchronizes-Shell-from-server',true);
    await select.selectOption(original);
    await page.waitForFunction(id=>{const f=document.querySelector('iframe');const data=f?.contentWindow?.localStorage.getItem('wavy-pwa-contexte');return data&&JSON.parse(data).societeCouranteId===Number(id);},original);
   }
   await page.locator('.sidebar .home').click();await page.locator('.panels').getByRole('button',{name:'Mobile PWA',exact:true}).click();
   await page.frameLocator('iframe[title="Module Wavy"]').locator('h1').waitFor();check('dashboard-opens-same-workspace',true);
   await page.locator('.sidebar').getByRole('button',{name:'Factures de vente',exact:true}).click();
   await page.frameLocator('iframe[title="Module Wavy"]').locator('h1,h2').first().waitFor();check('existing-Factures-navigation',true);
   const mobile=await c.newPage();await mobile.setViewportSize({width:390,height:844});await mobile.goto(origin+'/pwa/notes-frais');await mobile.locator('h1').waitFor();
   check('standalone-mobile-no-Shell',await mobile.locator('.sidebar').count()===0);
   const manifest=await read(mobile,'/pwa/manifest.webmanifest');const data=JSON.parse(manifest.text);
   check('same-installable-PWA',data.scope==='/pwa/'&&data.start_url==='/pwa/notes-frais'&&data.display==='standalone'&&data.icons.some(icon=>icon.sizes==='512x512'));
   await mobile.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration('/pwa/'))?.active,{},{timeout:45000});
   const scope=await mobile.evaluate(async()=>(await navigator.serviceWorker.getRegistration('/pwa/')).scope);
   check('service-worker-scoped-to-PWA',scope===origin+'/pwa/');
   check('service-worker-does-not-control-ERP',await page.evaluate(()=>navigator.serviceWorker.controller===null));
   const cdp=await c.newCDPSession(mobile);const installation=await cdp.send('Page.getInstallabilityErrors');
   result.installabilityErrors=installation.installabilityErrors;save();result.installationLimitation=installation.installabilityErrors.some(e=>e.errorId==='in-incognito')?'Actual installation unavailable in the isolated Chrome context':null;
   check('Chrome-installability-no-application-errors',installation.installabilityErrors.filter(e=>e.errorId!=='in-incognito').length===0);await cdp.detach();
   check('same-session-no-second-login',!mobile.url().includes('connexion'));
  }else{await page.waitForURL(origin+'/pwa/notes-frais');check('PWA-list-API',(await notes).status()===200);await page.locator('app-root h1').waitFor();}

  result.passed=true;save();await diag.finish(page);ready=true;
  process.stdout.write(JSON.stringify({kind:'ready',passed:true})+'\n');
  // Keep the dedicated manual window open; gate expiry never deletes business data.
  await new Promise(resolve=>browser.once('disconnected',resolve));
 }catch(error){save();await diag.finish(page,error);throw error;}
 finally{if(browser&&!ready)await browser.close();}
}
async function layout(){
 const [input,dir]=process.argv.slice(2),phase=process.argv[process.argv.indexOf('--layout')+1],f=JSON.parse(fs.readFileSync(input,'utf8'));
 const result={phase,passed:false,viewports:[],businessWrites:0,tlsVerified:true};let b;
 const save=()=>fs.writeFileSync(path.join(dir,'layout-results.json'),JSON.stringify(result,null,2));
 try{
  b=await chromium.launch({channel:'chrome',headless:false});const c=await b.newContext({ignoreHTTPSErrors:false,serviceWorkers:'block'});
  await c.route('**/*',route=>{
   const r=route.request(),u=new URL(r.url());
   if(u.origin!==origin||(!['GET','HEAD','OPTIONS'].includes(r.method())&&!(r.method()==='POST'&&u.pathname==='/api/auth/session')))return route.abort('blockedbyclient');
   return route.continue();
  });
  const page=await c.newPage();await page.goto(origin);await page.getByLabel('Adresse email').fill(f.Email);await page.getByLabel('Mot de passe').fill(f['Mot de passe']);
  await page.getByRole('button',{name:'Se connecter',exact:true}).click();await page.getByRole('heading',{name:/Bonjour/}).waitFor();
  for(const [width,height] of [[1366,768],[1600,900],[1920,1080]]){
   await page.setViewportSize({width,height});
   const views=[['dashboard',null],['tiers','Tous les tiers'],['contrats','Tous les contrats'],['factures','Factures de vente'],['tresorerie','Opérations bancaires'],['pwa','Mobile PWA']];
   views.push(['finance','Dashboard financier']);
   for(const [module,label]of views){
    // Direct Shell navigation also works when tablet mode collapses menu labels.
    if(module==='dashboard')await page.goto(origin+'/dashboard');
    else {const routes={tiers:'/tiers',contrats:'/contrats',factures:'/factures/ventes',tresorerie:'/tresorerie?vue=operations',pwa:'/notes-frais',finance:'/dashboard-financier'};
     await page.goto(origin+'/module?'+new URLSearchParams({module:module==='finance'?'factures':module,path:routes[module],label:label||module}));}
    if(module==='dashboard')await page.getByRole('heading',{name:/Bonjour/}).waitFor();
    else await page.frameLocator('iframe[title="Module Wavy"]').locator('h1,h2').first().waitFor();
    if(module==='finance')await page.frameLocator('iframe[title="Module Wavy"]').locator('canvas').first().waitFor({timeout:20000});
    await page.waitForTimeout(250);
    const geometry=await page.evaluate(()=>{
     const box=s=>{const el=document.querySelector(s);if(!el)return null;const r=el.getBoundingClientRect(),css=getComputedStyle(el);return {x:r.x,right:r.right,width:r.width,height:r.height,bottom:r.bottom,clientWidth:el.clientWidth,scrollWidth:el.scrollWidth,clientHeight:el.clientHeight,scrollHeight:el.scrollHeight,overflowY:css.overflowY,paddingLeft:css.paddingLeft,paddingRight:css.paddingRight};};
     const result={viewport:innerWidth,viewportHeight:innerHeight,rootWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth,rootScrollHeight:document.documentElement.scrollHeight,rootClientHeight:document.documentElement.clientHeight,erp:box('.erp'),sidebar:box('.sidebar'),main:box('.erp>main'),content:box('.content'),iframe:box('iframe[title="Module Wavy"]'),kpis:box('.kpis')};
     const frame=document.querySelector('iframe[title="Module Wavy"]');if(frame?.contentDocument){const d=frame.contentDocument;const el=d.querySelector('.page-shell:not(.narrow),.page-stack,.notes-page,.page,.app-main');const r=el?.getBoundingClientRect();const measure=el=>{if(!el)return null;const b=el.getBoundingClientRect(),s=getComputedStyle(el);return {tag:el.tagName,x:b.x,y:b.y,right:b.right,bottom:b.bottom,width:b.width,height:b.height,display:s.display,minHeight:s.minHeight,heightCss:s.height,paddingTop:parseFloat(s.paddingTop),paddingRight:parseFloat(s.paddingRight),paddingBottom:parseFloat(s.paddingBottom),paddingLeft:parseFloat(s.paddingLeft),maxWidth:s.maxWidth,overflow:s.overflow,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight};};
     const host=d.querySelector('.app-main>router-outlet+*');result.module={viewport:d.documentElement.clientWidth,viewportHeight:frame.contentWindow.innerHeight,scrollWidth:d.documentElement.scrollWidth,content:r?{x:r.x,right:r.right,width:r.width}:null,scrollHeight:d.documentElement.scrollHeight,clientHeight:d.documentElement.clientHeight,chain:{html:measure(d.documentElement),body:measure(d.body),app:measure(d.querySelector('app-root')),main:measure(d.querySelector('.app-main')||d.querySelector('.app-shell')),routeHost:measure(host),page:measure(host?.firstElementChild||d.querySelector('.notes-page'))}};}return result;
    });
    const filename=`${phase}-${width}-${module}.png`;
    await page.screenshot({path:path.join(dir,filename),mask:[page.locator('.profile span'),page.locator('header select'),page.locator('.welcome h1')],maskColor:'#dbe5ed'});
    const row={width,height,view:module,screenshot:filename,...geometry};
    row.passed=geometry.scrollWidth<=geometry.rootWidth+1&&Math.abs(geometry.erp.right-geometry.rootWidth)<=1&&Math.abs(geometry.erp.bottom-geometry.viewportHeight)<=1;
    if(geometry.module)row.passed=row.passed&&geometry.module.scrollWidth<=geometry.module.viewport+1;
    if(geometry.iframe){row.passed=row.passed&&geometry.rootScrollHeight<=geometry.rootClientHeight+1&&Math.abs(geometry.iframe.right-geometry.main.right)<=1&&Math.abs(geometry.iframe.bottom-geometry.viewportHeight)<=1;const chain=geometry.module.chain;for(const node of [chain.app,chain.main]){if(node)row.passed=row.passed&&node.width>=geometry.module.viewport-1&&node.bottom>=geometry.module.viewportHeight-1;}if(chain.routeHost){const host=chain.routeHost,main=chain.main;row.passed=row.passed&&host.width>=main.width-main.paddingLeft-main.paddingRight-1&&host.height>=main.height-main.paddingTop-main.paddingBottom-1;if(chain.page)row.passed=row.passed&&chain.page.height>=host.height-1;}}
    result.viewports.push(row);save();
   }
  }
  result.passed=phase==='before'||result.viewports.every(v=>v.passed);save();await b.close();
  process.stdout.write(JSON.stringify({kind:'ready',passed:result.passed})+'\n');
 }finally{save();if(b)await b.close();}
}
main().catch(()=>{console.error('Chrome Notes failed; inspect private sanitized results.');process.exitCode=1});
