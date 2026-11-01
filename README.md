# Wurmz API by Nat

Unofficial scraper API for [wurmz.net](https://wurmz.net).

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Health |
| GET | `/search?q=` | Search series |
| GET | `/popular?range=all\|today\|3d\|7d\|30d` | Popular |
| GET | `/latest` | Home latest updates |
| GET | `/list?sort=new` | All comics page |
| GET | `/series/{type}/{slug}` | Detail, synopsis, genres, chapters |
| GET | `/chapter/{type}/{slug}/{num}` | Chapter images (ads filtered) |

`type` = `manga` | `manhwa` | `manhua`

## Deploy (Vercel)

1. Push this folder to a GitHub repo  
2. Import on Vercel  
3. Deploy  

Example:
```
https://YOUR-APP.vercel.app/search?q=solo
https://YOUR-APP.vercel.app/series/manga/panduan-wanita-pemarah-untuk-membalas-dendam
https://YOUR-APP.vercel.app/chapter/manga/panduan-wanita-pemarah-untuk-membalas-dendam/53
```

## Notes

- Images often come from `cdn.voratoon.com`
- Cloudflare / upstream changes may cause occasional failures
- For adult sources, keep admin-only in the main app
