# Naughtyfish – Setup Guide
## Architecture Overview

```
Local machine (you)          Supabase (cloud DB)         Railway (web host)
─────────────────            ───────────────────         ──────────────────
Django + SQLite   ──sync──►  PostgreSQL tables   ◄──────  Django (reads DB)
Works offline ✓              Always up-to-date            Online access ✓
```

- **Local**: runs on your PC using SQLite. Works with zero internet.  
  Every save/delete automatically pushes changes to Supabase when connected.  
  If offline, changes queue locally and flush automatically when reconnected.

- **Supabase**: holds the PostgreSQL database.  
  Acts as the shared cloud copy of all your data.

- **Railway**: hosts the Django app online.  
  Connects directly to Supabase PostgreSQL via `DATABASE_URL`.  
  No separate sync needed — it reads/writes the same Supabase database.

---

## Step 1 – Supabase Setup

1. Log in to [supabase.com](https://supabase.com) and open your project.
2. Go to **SQL Editor → New query**.
3. Paste the entire contents of `SUPABASE_SCHEMA.sql` and click **Run**.
4. All tables will be created.
5. Go to **Project Settings → API** and copy:
   - **Project URL** → this is `SUPABASE_URL`
   - **anon public key** → this is `SUPABASE_KEY`
   - **Connection string** (URI format, port 5432) → this is `DATABASE_URL`

---

## Step 2 – Local Setup

1. Copy `.env.example` to `.env` and fill in your Supabase values:
   ```
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_KEY=eyJ...
   DATABASE_URL=          ← leave BLANK for local SQLite
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run migrations:
   ```bash
   python manage.py migrate
   ```
4. Start the app:
   ```bash
   python manage.py runserver
   ```
5. **First-time sync** – push all existing local data to Supabase:
   ```bash
   python manage.py sync_now
   ```

From now on, every change you make locally will automatically sync to Supabase
when your internet is connected. If you're offline, changes queue and sync
automatically when you reconnect.

---

## Step 3 – Deploy to Railway

1. Push your code to a GitHub repository.
2. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub**.
3. Select your repo.
4. Go to your Railway project → **Variables** and add:
   ```
   SECRET_KEY       = (generate a new secret key)
   DEBUG            = False
   ALLOWED_HOSTS    = your-app.railway.app
   DATABASE_URL     = postgresql://postgres:[pass]@db.[project].supabase.co:5432/postgres
   ```
   > **Where to find DATABASE_URL**: Supabase → Project Settings → Database → URI
5. Railway will auto-deploy. Your app will be live at `https://your-app.railway.app`.
6. On first deploy, run migrations via Railway's terminal:
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

---

## How Sync Works

| Situation | What happens |
|---|---|
| You're online and save a record locally | Instantly pushed to Supabase |
| You're offline and save a record | Queued in SQLite PendingSync table |
| Internet comes back | Worker thread flushes the queue automatically (within 60 sec) |
| Once per hour | Full sync runs to catch any missed records |
| Railway app adds/edits data | Writes directly to Supabase PostgreSQL |

---

## Useful Commands

```bash
# Force a full sync right now
python manage.py sync_now

# Check how many records are pending sync
python manage.py shell -c "from sync.models import PendingSync; print(PendingSync.objects.count())"

# Run migrations (always needed after pulling updates)
python manage.py migrate
```

---

## start_app.bat (Windows local launcher)

Your existing `start_app.bat` still works for local use. No changes needed.
