import type { AnalyzeResponse } from "../types";
import type { CacheEntry } from "./analyze";

const DB_NAME = "imslp-accompanist-android";
const DB_VERSION = 1;
const STORE = "analyses";

interface StoredAnalysis {
  key: string;
  pdf_name: string;
  timestamp: number;
  pdf_blob: Blob;
  analysis: AnalyzeResponse;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB open failed"));
  });
}

function requestValue<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error ?? new Error("IndexedDB transaction aborted"));
    tx.onerror = () => reject(tx.error ?? new Error("IndexedDB transaction failed"));
  });
}

async function pdfKey(pdf: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await pdf.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function toCacheEntry(item: StoredAnalysis): CacheEntry {
  return {
    key: item.key,
    param_set_id: "android-local",
    pdf_name: item.pdf_name,
    timestamp: item.timestamp,
    source: "local",
  };
}

export async function putAndroidCache(
  pdf: File,
  analysis: AnalyzeResponse,
): Promise<CacheEntry> {
  const db = await openDb();
  try {
    const item: StoredAnalysis = {
      key: await pdfKey(pdf),
      pdf_name: pdf.name,
      timestamp: Date.now() / 1000,
      pdf_blob: pdf.slice(0, pdf.size, pdf.type || "application/pdf"),
      analysis,
    };
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(item);
    await transactionDone(tx);
    return toCacheEntry(item);
  } finally {
    db.close();
  }
}

export async function listAndroidCache(): Promise<CacheEntry[]> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readonly");
    const rows = await requestValue(
      tx.objectStore(STORE).getAll() as IDBRequest<StoredAnalysis[]>,
    );
    await transactionDone(tx);
    return rows
      .sort((a, b) => b.timestamp - a.timestamp)
      .map(toCacheEntry);
  } finally {
    db.close();
  }
}

export async function getAndroidCache(
  key: string,
): Promise<{ analysis: AnalyzeResponse; pdf: File }> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readonly");
    const row = await requestValue(
      tx.objectStore(STORE).get(key) as IDBRequest<StoredAnalysis | undefined>,
    );
    await transactionDone(tx);
    if (!row) throw new Error("Local cache entry not found");
    return {
      analysis: row.analysis,
      pdf: new File([row.pdf_blob], row.pdf_name, {
        type: row.pdf_blob.type || "application/pdf",
      }),
    };
  } finally {
    db.close();
  }
}

export async function deleteAndroidCache(key: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(key);
    await transactionDone(tx);
  } finally {
    db.close();
  }
}

export async function touchAndroidCache(key: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const row = await requestValue(
      store.get(key) as IDBRequest<StoredAnalysis | undefined>,
    );
    if (row) {
      row.timestamp = Date.now() / 1000;
      store.put(row);
    }
    await transactionDone(tx);
  } finally {
    db.close();
  }
}
