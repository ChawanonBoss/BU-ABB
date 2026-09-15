(function(){
  const store = {};
  const listeners = {};
  const docListeners = {};
  function getColl(name){ if(!store[name]) store[name] = new Map(); return store[name]; }
  function notify(name){
    (listeners[name]||[]).forEach(l => l.fire());
    (docListeners[name]||[]).forEach(l => l.fire());
  }
  const FV_DELETE = '__FV_DELETE__';

  function applyPatch(obj, patch){
    for (const k in patch){
      if (patch[k] === FV_DELETE) delete obj[k];
      else obj[k] = patch[k];
    }
  }

  function snapshotDocs(name, filters){
    const coll = getColl(name);
    let docs = Array.from(coll.entries()).map(([id,data])=>({id,data}));
    (filters.wheres||[]).forEach(w => {
      docs = docs.filter(d => {
        const v = d.data[w.field];
        if (w.op === '==') return v === w.value;
        if (w.op === '>=') return v >= w.value;
        if (w.op === '<') return v < w.value;
        if (w.op === '<=') return v <= w.value;
        if (w.op === '>') return v > w.value;
        return true;
      });
    });
    if (filters.orderByField){
      docs = docs.filter(d => d.data[filters.orderByField] !== undefined);
      docs.sort((a,b)=>{
        const av=a.data[filters.orderByField], bv=b.data[filters.orderByField];
        const cmp = av>bv?1:av<bv?-1:0;
        return filters.orderDir==='desc' ? -cmp : cmp;
      });
    }
    if (filters.startAfterVal !== undefined){
      docs = docs.filter(d=>{
        const v = d.data[filters.orderByField];
        return filters.orderDir==='desc' ? v < filters.startAfterVal : v > filters.startAfterVal;
      });
    }
    if (filters.limitN) docs = docs.slice(0, filters.limitN);
    return docs;
  }

  function makeQuery(name, filters){
    filters = filters || {};
    return {
      where(field, op, value){ return makeQuery(name, Object.assign({}, filters, {wheres: (filters.wheres||[]).concat([{field,op,value}])})); },
      orderBy(f,dir){ return makeQuery(name, Object.assign({}, filters, {orderByField:f, orderDir:dir||'asc'})); },
      startAfter(v){ return makeQuery(name, Object.assign({}, filters, {startAfterVal:v})); },
      limit(n){ return makeQuery(name, Object.assign({}, filters, {limitN:n})); },
      get(){
        const docs = snapshotDocs(name, filters);
        return Promise.resolve({ docs: docs.map(d=>({id:d.id, data:()=>Object.assign({}, d.data)})), empty: docs.length===0 });
      },
      onSnapshot(cb, errCb){
        const fire = () => {
          const docs = snapshotDocs(name, filters);
          cb({ docs: docs.map(d=>({id:d.id, data:()=>Object.assign({}, d.data)})), empty: docs.length===0 });
        };
        if (!listeners[name]) listeners[name] = [];
        const entry = { fire };
        listeners[name].push(entry);
        fire();
        return () => { listeners[name] = listeners[name].filter(l=>l!==entry); };
      },
      doc(id){
        id = id || ('auto_'+Math.random().toString(36).slice(2));
        return {
          id,
          get(){ const coll=getColl(name); return Promise.resolve({ exists: coll.has(id), id, data: ()=>Object.assign({}, coll.get(id)) }); },
          set(data, opts){ const coll=getColl(name); const cur=coll.get(id)||{}; coll.set(id, (opts&&opts.merge)?Object.assign({},cur,data):Object.assign({},data)); notify(name); return Promise.resolve(); },
          update(patch){ const coll=getColl(name); const cur=coll.get(id)||{}; applyPatch(cur, patch); coll.set(id, cur); notify(name); return Promise.resolve(); },
          delete(){ const coll=getColl(name); coll.delete(id); notify(name); return Promise.resolve(); },
          // Re-fires on every write to ANY doc in this collection (not just this id) — matches
          // the collection-level listener above rather than trying to diff per-doc, which is
          // wasteful for a test mock but was a real gap before: this used to fire once at
          // registration and never again, silently hiding any code path that relies on a
          // single-doc listener observing its own later writes (e.g. commissionConfig/default).
          onSnapshot(cb){
            const coll = getColl(name);
            const fire = () => cb({ exists: coll.has(id), id, data: ()=>Object.assign({}, coll.get(id)) });
            if (!docListeners[name]) docListeners[name] = [];
            const entry = { fire };
            docListeners[name].push(entry);
            fire();
            return () => { docListeners[name] = docListeners[name].filter(l=>l!==entry); };
          },
        };
      },
      add(data){ const id='auto_'+Math.random().toString(36).slice(2); getColl(name).set(id,Object.assign({},data)); notify(name); return Promise.resolve({id}); },
    };
  }

  window.__mockStore = store;

  window.firebase = {
    initializeApp: () => ({}),
    auth: () => ({
      // Registers every listener (not just the first) and stores them on window.__authListeners
      // so a test can simulate a real sign-out via auth.signOut() and have onAuthStateChanged's
      // signed-out branch actually run — the real SDK always defers this callback, so anything
      // that only works because it fires synchronously here is a red flag, not a feature to rely on.
      onAuthStateChanged: (cb) => { window.__authListeners = window.__authListeners || []; window.__authListeners.push(cb); cb(null); },
      signInWithEmailAndPassword: () => Promise.reject(new Error('stub')),
      signOut: () => { (window.__authListeners||[]).forEach(cb => cb(null)); return Promise.resolve(); },
    }),
    firestore: Object.assign(() => ({
      collection: (name) => makeQuery(name),
      batch: () => {
        const ops = [];
        const api = {
          update(ref, patch){ ops.push(() => ref.update(patch)); return api; },
          set(ref, data, opts){ ops.push(() => ref.set(data, opts)); return api; },
          delete(ref){ ops.push(() => ref.delete()); return api; },
          async commit(){ for (const op of ops) await op(); },
        };
        return api;
      },
    }), {
      FieldValue: { delete: () => FV_DELETE }
    }),
  };
})();
