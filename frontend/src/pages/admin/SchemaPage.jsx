import { useEffect, useRef, useState } from "react";
import { getSchemaOverview, getTablePreview } from "../../api/schema.api";
import RoleGate from "../../components/RoleGate";

const VIEW_DATA = "data";
const VIEW_STRUCTURE = "structure";

function DataPreviewTable({ rows }) {
  if (rows.length === 0) {
    return <p className="text-sm text-text-muted">此資料表目前沒有資料。</p>;
  }
  const columns = Object.keys(rows[0]);
  return (
    <>
      <div data-testid="schema-data-cards" className="space-y-3 lg:hidden">
        {rows.map((row, index) => (
          <div key={index} className="glass-panel space-y-2 rounded-xl p-4">
            {columns.map((column) => (
              <div key={column}>
                <dt className="text-xs text-text-muted">{column}</dt>
                <dd className="mt-0.5 break-all text-sm text-text-primary">
                  {row[column] === null || row[column] === undefined ? "—" : String(row[column])}
                </dd>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="hidden glass-panel overflow-x-auto rounded-xl lg:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              {columns.map((column) => (
                <th key={column} className="whitespace-nowrap px-4 py-3">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-border-subtle last:border-0">
                {columns.map((column) => (
                  <td key={column} className="whitespace-nowrap px-4 py-3 text-text-primary">
                    {row[column] === null || row[column] === undefined ? "—" : String(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function StructureTable({ columns }) {
  return (
    <>
      <div data-testid="schema-structure-cards" className="space-y-3 lg:hidden">
        {columns.map((column) => (
          <div key={column.name} className="glass-panel space-y-2 rounded-xl p-4">
            <p className="text-base font-medium text-text-primary">{column.name}</p>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <dt className="text-text-muted">型別</dt>
                <dd className="text-text-secondary">{column.type}</dd>
              </div>
              <div>
                <dt className="text-text-muted">可為 NULL</dt>
                <dd className="text-text-secondary">{column.nullable ? "是" : "否"}</dd>
              </div>
              <div>
                <dt className="text-text-muted">主鍵</dt>
                <dd className="text-text-secondary">{column.is_primary_key ? "是" : "—"}</dd>
              </div>
              <div>
                <dt className="text-text-muted">外鍵參照</dt>
                <dd className="text-text-secondary">
                  {column.is_foreign_key ? `${column.references.table}.${column.references.column}` : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-text-muted">預設值</dt>
                <dd className="text-text-secondary">{column.default ?? "—"}</dd>
              </div>
            </dl>
          </div>
        ))}
      </div>

      <div className="hidden glass-panel overflow-x-auto rounded-xl lg:block">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border-subtle text-text-muted">
              <th className="px-4 py-3">欄位名稱</th>
              <th className="px-4 py-3">型別</th>
              <th className="px-4 py-3">可為 NULL</th>
              <th className="px-4 py-3">主鍵</th>
              <th className="px-4 py-3">外鍵參照</th>
              <th className="px-4 py-3">預設值</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column) => (
              <tr key={column.name} className="border-b border-border-subtle last:border-0">
                <td className="px-4 py-3 text-text-primary">{column.name}</td>
                <td className="px-4 py-3 text-text-primary">{column.type}</td>
                <td className="px-4 py-3 text-text-primary">{column.nullable ? "是" : "否"}</td>
                <td className="px-4 py-3 text-text-primary">{column.is_primary_key ? "是" : "—"}</td>
                <td className="px-4 py-3 text-text-primary">
                  {column.is_foreign_key ? `${column.references.table}.${column.references.column}` : "—"}
                </td>
                <td className="px-4 py-3 text-text-primary">{column.default ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SchemaContent() {
  const [tables, setTables] = useState({});
  const [selectedTable, setSelectedTable] = useState("");
  const [view, setView] = useState(VIEW_DATA);
  const [displayedRows, setDisplayedRows] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingRows, setIsLoadingRows] = useState(false);
  // 切換過的表快取，不重複打 API（見 docs/UI-SPEC.md §3.16）。
  const previewCache = useRef(new Map());

  useEffect(() => {
    // StrictMode 在開發模式下會把這個 effect 掛載→清除→再掛載一次；沒有這個
    // cancelled guard 的話，第一次掛載那個沒被中止的 fetch 晚點回來時，
    // 會用預設表名覆蓋掉使用者當下已經手動選好的表。
    let cancelled = false;
    getSchemaOverview().then(({ tables: allTables }) => {
      if (cancelled) return;
      setTables(allTables);
      const sortedNames = Object.keys(allTables).sort();
      setSelectedTable(sortedNames[0] ?? "");
      setIsLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedTable || view !== VIEW_DATA) return undefined;

    if (previewCache.current.has(selectedTable)) {
      setDisplayedRows(previewCache.current.get(selectedTable));
      return undefined;
    }

    let cancelled = false;
    setIsLoadingRows(true);
    getTablePreview(selectedTable).then(({ rows }) => {
      if (cancelled) return;
      previewCache.current.set(selectedTable, rows);
      setDisplayedRows(rows);
      setIsLoadingRows(false);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedTable, view]);

  if (isLoading) {
    return <p className="text-sm text-text-muted">載入中…</p>;
  }

  const tableNames = Object.keys(tables).sort();

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-medium text-text-primary">資料庫管理</h2>

      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="schema-table" className="mb-1 block text-xs text-text-muted">
            資料表
          </label>
          <select
            id="schema-table" value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}
            className="rounded-lg border border-border-subtle bg-surface-900 px-3 py-2 text-sm text-text-primary"
          >
            {tableNames.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <button
            type="button" onClick={() => setView(VIEW_DATA)}
            className={`rounded-lg px-3 py-2 text-sm ${view === VIEW_DATA ? "bg-surface-700 text-accent-400" : "text-text-secondary hover:bg-surface-800"}`}
          >
            資料內容
          </button>
          <button
            type="button" onClick={() => setView(VIEW_STRUCTURE)}
            className={`rounded-lg px-3 py-2 text-sm ${view === VIEW_STRUCTURE ? "bg-surface-700 text-accent-400" : "text-text-secondary hover:bg-surface-800"}`}
          >
            結構定義
          </button>
        </div>
      </div>

      {view === VIEW_DATA &&
        (isLoadingRows ? <p className="text-sm text-text-muted">載入中…</p> : <DataPreviewTable rows={displayedRows} />)}
      {view === VIEW_STRUCTURE && <StructureTable columns={tables[selectedTable] ?? []} />}
    </div>
  );
}

export default function SchemaPage() {
  return (
    <RoleGate roles={["admin"]}>
      <SchemaContent />
    </RoleGate>
  );
}
