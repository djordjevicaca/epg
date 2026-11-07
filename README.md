# EPG za srpske kanale

Svaki dan GitHub Actions povuče program sa mts.rs i objavi XMLTV sa ID-jevima kanala IPTV provajdera.

- EPG URL: `https://<user>.github.io/epg/epg.xml.gz` (ili `epg.xml`)
- Mapiranje kanala: `mapping.json` (ID provajdera → kod kanala na mts.rs)
- Ručno pokretanje: Actions → grab-epg → Run workflow
