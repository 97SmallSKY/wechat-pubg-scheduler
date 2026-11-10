import {readFileSync} from "node:fs";
import {DatabaseSync} from "node:sqlite";

export function newDB() {
  const sqlite = new DatabaseSync(":memory:");
  sqlite.exec(readFileSync(new URL("../drizzle/0000_scheduler.sql", import.meta.url), "utf8"));
  return {
    prepare(sql) {
      const statement = sqlite.prepare(sql);
      let args = [];
      return {
        bind(...params) { args = params; return this; },
        first() { return statement.get(...args) ?? null; },
        run() { return statement.run(...args); },
        execute() { return {results: statement.columns().length ? statement.all(...args) : (statement.run(...args), [])}; },
      };
    },
    async batch(statements) {
      sqlite.exec("BEGIN");
      try {
        const results = statements.map(statement => statement.execute());
        sqlite.exec("COMMIT");
        return results;
      } catch (error) {
        sqlite.exec("ROLLBACK");
        throw error;
      }
    },
  };
}
