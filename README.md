# SongAI
AI model for educational purposes only.

## Başlangıç (Otomatik Scraping İskeleti)
Bu repo, otomatik web scraping + veri depolama akışının temelini atar. Amaç, ileride
RAG (retrieval augmented generation) ve model eğitimi için bir veri gölü oluşturmaktır.
Bu aşama **model eğitmez**; veri toplar, yerel indeks oluşturur ve basit arama/cevap
mekanizması sağlar. LLM eğitimi için ayrıca eğitim altyapısı gerekir.

### Kurulum
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Örnek kullanım
Aşağıdaki komut, sadece belirlediğiniz domain içinde kalır ve SQLite veritabanına veri yazar.

```bash
PYTHONPATH=src python -m songai scrape \
  --start-url "https://example.com" \
  --allowed-domain "example.com" \
  --max-pages 25 \
  --output-db data/songai.db
```

Sürekli (7/24) çalıştırmak için:

```bash
PYTHONPATH=src python -m songai scrape \
  --start-url "https://example.com" \
  --allowed-domain "example.com" \
  --continuous \
  --idle-sleep-s 300 \
  --output-db data/songai.db
```

Not: `--max-pages 0` sınırsız tarama anlamına gelir.

Basit arama:

```bash
PYTHONPATH=src python -m songai search \
  --query "knowledge base" \
  --output-db data/songai.db \
  --limit 5
```

İndeksleme (öğrenme):

```bash
PYTHONPATH=src python -m songai learn \
  --output-db data/songai.db
```

Sürekli öğrenme:

```bash
PYTHONPATH=src python -m songai learn \
  --continuous \
  --idle-sleep-s 300 \
  --output-db data/songai.db
```

Basit cevaplama (indeks üzerinden):

```bash
PYTHONPATH=src python -m songai answer \
  --query "learning pipeline" \
  --output-db data/songai.db \
  --limit 3
```

Hepsi bir arada (scrape + learn) sürekli çalıştırma:

```bash
PYTHONPATH=src python -m songai run \
  --start-url "https://example.com" \
  --allowed-domain "example.com" \
  --max-pages 0 \
  --crawl-delay-s 1 \
  --learn-idle-sleep-s 60 \
  --output-db data/songai.db
```

Durum kontrolü:

```bash
PYTHONPATH=src python -m songai status \
  --output-db data/songai.db
```

### Çıktı
Scraping tamamlandığında `data/songai.db` içinde `documents` tablosu oluşur.
URL kuyruğu `url_queue` tablosunda tutulur ve yarıda kalsa bile devam edebilir.
İndeks tabloları (`doc_index`, `doc_stats`, `doc_index_meta`) öğrenme aşamasının
devam edebilmesini sağlar.
İçerik hash'i ile tekrar eden dokümanlar otomatik ayıklanır ve metin normalize edilir.

## Sonraki Adımlar (Öneri)
- Temizleme + deduplikasyon katmanı
- Embedding üretimi ve vektör veritabanı entegrasyonu
- RAG sorgu katmanı ve küçük bir LLM ile cevap üretimi
