from django.db import connection
with connection.cursor() as c:
    c.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='buildwatch_subcontractarrangement'
      ORDER BY column_name
    """)
    cols = [r[0] for r in c.fetchall()]
print("has quote_status", "quote_status" in cols)
print("cols sample", [x for x in cols if x.startswith("quote") or x.startswith("award") or x.startswith("included")])
c2 = connection.cursor()
c2.execute("SELECT app, name FROM django_migrations WHERE app='buildwatch' ORDER BY id")
print("migrations", c2.fetchall())
c2.execute("SELECT to_regclass('buildwatch_subcontractquoteline')")
print("quoteline table", c2.fetchone())
