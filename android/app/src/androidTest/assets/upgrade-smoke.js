(async () => {
  const checks = [];
  const key = "imslp-accompanist.omr-server.v1";
  const url = "http://127.0.0.1:18765";
  const token = "upgrade-smoke-token"; // A synthetic test token, never a user's credential.
  const pdfText = "%PDF-1.4\n% upgrade persistence fixture\n";
  const xml = '<?xml version="1.0"?><score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part></score-partwise>';
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const wait = async (fn, message) => {
    const deadline = Date.now() + 15000;
    while (!await fn()) {
      if (Date.now() > deadline) throw Error(message);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  };
  const open = async () => {
    document.querySelector(".mobile-topbar__settings").click();
    await wait(() => document.querySelector(".server-settings select"), "Settings did not open");
  };
  const setInput = (el, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, value);
    el.dispatchEvent(new Event("input", {bubbles:true}));
  };
  const select = value => {
    const el = document.querySelector(".server-settings select");
    el.value = value;
    el.dispatchEvent(new Event("change", {bubbles:true}));
  };
  const readRows = () => new Promise((resolve,reject) => {
    const request = indexedDB.open("imslp-accompanist-android",1);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const tx = db.transaction("analyses","readonly");
      const r = tx.objectStore("analyses").getAll();
      let rows;
      r.onsuccess = () => {rows=r.result;};
      tx.oncomplete = () => {db.close();resolve(rows);};
      tx.onabort = () => {db.close();reject(tx.error);};
    };
  });
  const config = () => JSON.parse(localStorage.getItem(key));
  if (window.__UPGRADE_PHASE__ === "seed") {
    await open();
    assert(document.querySelector(".server-settings select").value === "audiveris", "Old fresh default changed");
    document.querySelector(".server-settings__close").click();
    [...document.querySelectorAll(".lang-switch__opt")].find(el => el.textContent === "English").click();
    await wait(() => localStorage.getItem("lang")==="en","Language not saved");
    await open();
    setInput(document.querySelector(".server-settings input:not([type=password])"),url);
    setInput(document.querySelector(".server-settings input[type=password]"),token);
    select("homr");
    await new Promise((resolve,reject) => {
      const request=indexedDB.open("imslp-accompanist-android",1);
      request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("analyses")) request.result.createObjectStore("analyses",{keyPath:"key"});};
      request.onerror=()=>reject(request.error);
      request.onsuccess=()=>{
        const db=request.result;
        const tx=db.transaction("analyses","readwrite");
        tx.objectStore("analyses").put({
          key:"upgrade-smoke:audiveris",pdf_name:"upgrade-smoke.pdf",timestamp:1234567890,
          pdf_blob:new Blob([pdfText],{type:"application/pdf"}),engine:"audiveris",
          analysis:{music_xml:xml,accompaniment_part_id:"P1",solo_part_id:null,measures:[],divisions:1,tempo_bpm:100,time_signature:{beats:4,beat_type:4},page_sizes:[],warnings:[],omr_engine:"audiveris"}
        });
        tx.oncomplete=()=>{db.close();resolve();};
        tx.onabort=()=>{db.close();reject(tx.error);};
      };
    });
    document.querySelector(".server-settings__save").click();
    await wait(()=>config()?.omrEngine==="homr","Old UI did not persist engine");
    assert(config().serverUrl===url && config().apiToken===token,"Old UI did not save settings");
    await wait(()=>document.body.textContent.includes("upgrade-smoke.pdf"),"Old cache entry not displayed");
    checks.push("v0.2.3 settings saved through UI", "language saved", "PDF/analysis stored in old WebView IndexedDB");
  } else if (window.__UPGRADE_PHASE__ === "verify") {
    assert(config()?.serverUrl===url && config()?.apiToken===token && config()?.omrEngine==="homr","Settings lost on update");
    assert(localStorage.getItem("lang")==="en","Language lost on update");
    const rows=await readRows();
    const legacy=rows.find(row=>row.key==="upgrade-smoke:audiveris");
    assert(legacy && legacy.analysis.music_xml===xml && legacy.engine==="audiveris","Analysis lost or altered");
    assert(await legacy.pdf_blob.text()===pdfText,"Stored PDF bytes changed");
    await wait(()=>document.body.textContent.includes("upgrade-smoke.pdf"),"Restored history not displayed");
    checks.push("server URL/token/engine retained", "language retained", "PDF bytes and MusicXML retained", "history displayed after update");
    await open();
    const options=[...document.querySelector(".server-settings select").options].map(o=>o.value).sort();
    assert(JSON.stringify(options)===JSON.stringify(["audiveris","homr","hybrid"]), "Three engine choices missing");
    assert(document.querySelector(".server-settings select").value==="homr","Saved engine not reflected in UI");
    select("hybrid");
    await new Promise(resolve => setTimeout(resolve,100));
    document.querySelector(".server-settings__save").click();
    await wait(()=>config().omrEngine==="hybrid","Hybrid selection not saved");
    checks.push("Audiveris/homr/Hybrid selectable");
    const choose = () => {
      const input=document.querySelector("input[type=file]");
      assert(input && !input.disabled,"File input disabled");
      const transfer=new DataTransfer();
      transfer.items.add(new File([pdfText],"hybrid-smoke.pdf",{type:"application/pdf"}));
      input.files=transfer.files;
      input.dispatchEvent(new Event("change",{bubbles:true}));
    };
    choose();
    await wait(()=>document.body.textContent.includes("ハイブリッドOMR"),"Unsupported server error did not appear");
    let state=await (await fetch(url+"/test/state")).json();
    assert(state.uploads.length===0 && state.capabilities>0,"PDF uploaded to unsupported server");
    checks.push("unsupported Hybrid server rejected before upload");
    await fetch(url+"/test/support",{method:"POST"});
    choose();
    await wait(async()=>((await (await fetch(url+"/test/state")).json()).uploads.length===1),"Supported request not received");
    await wait(()=>document.querySelector(".score-area svg"),"Returned MusicXML did not render");
    state=await (await fetch(url+"/test/state")).json();
    assert(state.uploads[0].engine==="hybrid" && state.uploads[0].authorized && state.uploads[0].pdf_name==="hybrid-smoke.pdf","Hybrid request fields incorrect");
    const updatedRows=await readRows();
    assert(updatedRows.some(row=>row.engine==="hybrid" && row.pdf_name==="hybrid-smoke.pdf"),"Hybrid result not cached");
    assert(updatedRows.some(row=>row.key==="upgrade-smoke:audiveris"),"Hybrid caching overwrote previous analysis");
    checks.push("supported server receives Hybrid request and token", "fixture MusicXML rendered and Hybrid cached separately");
  } else if (window.__UPGRADE_PHASE__ === "fresh") {
    assert(localStorage.getItem(key)===null,"Fresh test must start with empty data");
    await open();
    assert(document.querySelector(".server-settings select").value==="audiveris","New fresh default changed");
    checks.push("v0.2.4 fresh default remains Audiveris");
  } else {
    throw Error("Unknown phase");
  }
  window.__UPGRADE_RESULT__={passed:true,checks};
})().catch(error=>{window.__UPGRADE_RESULT__={error:String(error.stack || error)};});