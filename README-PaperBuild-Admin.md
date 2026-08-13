# PaperBuild Admin

Start the website:

```bat
start-paperbuild.bat
```

Open:

- Public website: `http://localhost:8000`
- Admin dashboard: `http://localhost:8000/admin`

The first visit to `/admin` asks you to create the admin password. The password hash is stored in `data/paperbuild.db`, not in frontend code.

PDF uploads are stored in `private_uploads/` and are never served by direct URL. Free downloads require an email token. Paid downloads only unlock when the order status is changed to `Paid` in the admin dashboard or by a future payment verification integration.
