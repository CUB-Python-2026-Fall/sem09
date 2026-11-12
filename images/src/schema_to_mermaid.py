"""Build the app's real SQLite schema, read it back, and write a Mermaid ER diagram."""
import sqlite3, sys, tempfile, os
sys.path.insert(0, sys.argv[1])
from askboard.database import create_tables
db = os.path.join(tempfile.mkdtemp(), "schema.db")
create_tables(db)
con = sqlite3.connect(db)
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
lines = ["erDiagram"]
for t in tables:
    fks = {r[3]: r for r in con.execute(f"PRAGMA foreign_key_list({t})")}
    uniq = set()
    for idx in con.execute(f"PRAGMA index_list({t})"):
        if idx[2]:
            uniq |= {r[2] for r in con.execute(f"PRAGMA index_info({idx[1]})")}
    lines.append(f"    {t} {{")
    for cid, name, typ, notnull, dflt, pk in con.execute(f"PRAGMA table_info({t})"):
        keys = [k for k, on in (("PK", pk), ("FK", name in fks), ("UK", name in uniq and not pk)) if on]
        note = "NOT NULL" if notnull and not pk else ""
        lines.append(f"        {typ} {name} {','.join(keys)} {('\"'+note+'\"') if note else ''}".rstrip())
    lines.append("    }")
for t in tables:
    for r in con.execute(f"PRAGMA foreign_key_list({t})"):
        lines.append(f'    {r[2]} ||--o{{ {t} : "{r[3]} -> {r[2]}.{r[4]}"')
print("\n".join(lines))
