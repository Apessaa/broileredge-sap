# Presentasi Singkat untuk Pakar: teks slide dan naskah

Pengarahan berbahasa Indonesia untuk langkah 2 di PROTOCOL.md (sekitar 8 menit, sama untuk setiap pakar).
Naskah diambil dari catatan pembicara di setiap slide.

## Slide 1: Dari Pembacaan Sensor Kandang ke Tugas dan Laporan Harian di SAP

- Evaluasi pakar · pengarahan singkat
- Rancangan sistem IoT berbasis aturan untuk kandang broiler closed house
- Zona inlet · 0–40 m
- Zona tengah · 40–80 m
- Zona exhaust · 80–120 m
- Rancangan: makalah v34 · katalog tugas 2026-10-v2 · sekitar 8 menit

*Naskah:* Terima kasih sudah membaca dan menyetujui halaman pertama formulir. Selama sekitar delapan menit saya akan menjelaskan rancangan sistem yang akan Bapak/Ibu nilai di Bagian A dan B. Saya hanya menjelaskan cara kerja rancangannya, tidak membelanya. Silakan bertanya bila ada yang kurang jelas. Penilaian yang jujur, termasuk ketidaksetujuan, adalah yang kami butuhkan.

## Slide 2: Kondisi kandang belum sampai ke sistem bisnis

- 01 · Masalah
- **Pemantauan saat ini:** Controller menggerakkan cooling pad dan kipas exhaust berdasarkan suhu kandang; NH₃ sering diperiksa dengan kertas indikator.
- **Tidak tercatat di SAP:** Kami tidak menemukan deskripsi pembacaan kandang yang masuk ke sistem bisnis yang merencanakan pakan, panen dan pemeliharaan.
- **Tindak lanjut tidak terlacak:** Apa yang dilakukan staf terhadap suatu kondisi, dan apakah itu membantu, tidak dicatat.
- Tujuan rancangan
- Mengubah pembacaan kandang menjadi penilaian, kemungkinan penyebab dan tugas yang tercatat di SAP, lalu dilaporkan setiap hari beserta apakah tugas sudah dikerjakan.

*Naskah:* Di kandang closed house, controller menggerakkan cooling pad dan kipas berdasarkan suhu kandang, dan NH3 sering diperiksa dengan kertas indikator. Dalam literatur yang kami tinjau, kami tidak menemukan pembacaan kandang yang masuk ke sistem bisnis seperti SAP, yang merencanakan pakan, panen dan pemeliharaan. Apa yang dilakukan staf terhadap suatu kondisi, dan apakah itu membantu, juga tidak tercatat. Rancangan ini mencoba menutup celah itu: dari pembacaan sensor sampai tugas yang tercatat di SAP dan laporan harian.

## Slide 3: Satu pembacaan, dua jalur

- 02 · Alur sistem
- 1. Sensor mengukur di tiga zona
- 2. Bus RS-485 membawa data ke Raspberry Pi
- 3. Penilaian zona, kemungkinan penyebab, tugas
- Membaca setiap 60 detik dan menilai setiap 5 menit. Setelah langkah 3, jalur a dan b berjalan bersamaan.
- a · Di lokasi: kepala kandang dan staf
- 4a. Pemberitahuan / peringatan ke kepala kandang
- 5a. Staf bertindak di kandang
- Jalur a tetap berjalan tanpa internet atau SAP.
- b · Ke SAP: dicatat, dieskalasi, dilaporkan
- 4b. Outbox lokal di Raspberry Pi
- 5b. Middleware (REST, lalu SOAP ke SAP)
- 6b. Disimpan sekali di SAP
- 7b. Notifikasi PM pada episode Berat ke-3
- 8b. Tugas ditandai selesai (staf / kantor farm)
- 9b. Laporan harian ke manajer farm

*Naskah:* Ini alur satu pembacaan, sama dengan Gambar 1 di makalah. Langkah 1 sampai 3 terjadi di kandang dan di Raspberry Pi di kantor farm: sensor mengukur, bus RS-485 membawa data, dan Raspberry Pi menilai setiap zona serta memilih kemungkinan penyebab dan tugas. Setelah itu ada dua jalur yang berjalan bersamaan. Jalur a di lokasi: kepala kandang mendapat pemberitahuan atau peringatan, lalu staf bertindak; jalur ini tidak memerlukan internet. Jalur b ke SAP: penilaian keluar melalui outbox dan middleware, disimpan sekali, dan pada episode Berat ketiga dibuka notifikasi Plant Maintenance. Staf atau kantor farm menandai tugasnya selesai, dan setiap pagi ada laporan per kandang. Slide berikutnya menjelaskan tiap bagian.

## Slide 4: Lima parameter, tiga zona, satu kabel

- 03 · Sensor dan penempatan
- Zona inlet · 0–40 m
- Zona tengah · 40–80 m
- Zona exhaust · 80–120 m
- Cooling pad di sisi inlet
- Kandang 120 m × 12 m · udara: inlet → exhaust
- Kipas exhaust di dinding ujung
- **Sentera ODMHM-R × 3:** Suhu, RH dan CO₂ di tengah tiap zona: 20, 60 dan 100 m
- **Seeed S-NH3-01 × 2:** NH₃ di tempat gas menumpuk: 64 dan 104 m; galat tipikal ±5 ppm
- **Delta OHM HD53LS.S × 1:** Kecepatan angin pada 56 m, untuk pemeriksaan angin rendah
- **Raspberry Pi di kantor farm:** Satu kabel RS-485 (Modbus RTU) melewati ketiga zona; UPS dan outbox lokal
- Semua sensor dipasang setinggi ayam dan dicek dengan pembacaan manual sekali per flock.

*Naskah:* Kandang acuan berukuran 120 kali 12 meter, dengan cooling pad di sisi inlet dan kipas exhaust di dinding ujung. Kandang dibagi tiga zona masing-masing 40 meter. Di tengah tiap zona ada satu sensor suhu, kelembapan dan CO2. Dua sensor NH3 dipasang di 64 dan 104 meter, tempat amonia cenderung menumpuk; galat tipikal sensor ini plus minus 5 ppm. Satu anemometer di 56 meter dipakai untuk pemeriksaan angin rendah. Semua sensor setinggi ayam, terhubung pada satu kabel RS-485 ke Raspberry Pi di kantor farm, yang punya UPS dan outbox lokal. Pemilihan sensor terutama karena ketiganya memakai protokol Modbus RTU yang sama.

## Slide 5: Setiap 5 menit: Normal, Sedang atau Berat

- 04 · Aturan penilaian
| Indikator (berlaku) | Normal | Sedang | Berat | Sumber |
|---|---|---|---|---|
| THI (umur ≥ 21 hari) | < 26 | 26–29 | > 29 | Omomowo & Falayi 2021 |
| \|Suhu − T*\|, °C (umur < 21 hari) | ≤ 2 | > 2 sampai 4 | > 4 | Ross Pocket Guide 2025 |
| NH₃, ppm | ≤ 10 | > 10 sampai 20 | > 20 | Ross 2025; Direktif UE 2007/43 |
| CO₂, ppm | ≤ 3.000 | > 3.000 sampai 3.500 | > 3.500 | Ross 2025; Direktif UE 2007/43 |
| THVI, °C (hanya catatan, ≥ 21 hari) | < 35 | 35–38 | > 38 | Tao & Xin 2003 |

- T*: suhu target menurut bobot sampel terbaru dan RH (tabel Ross). Kelas THI berasal dari studi ayam petelur. Semua batas adalah parameter berversi, untuk dikalibrasi di lapangan.
- **Persistensi:** Naik setelah 2 jendela berturut-turut, turun setelah 3.
- **Tingkat kandang:** Zona terburuk menentukan tingkat seluruh kandang.
- **Verifikasi NH₃:** NH₃ dalam ±5 ppm dari batas kelas: cek dengan kertas indikator; tingkat tetap.
- **Hanya catatan:** THVI dan cek angin rendah (mulai minggu ke-4: THI ≥ 26, angin < 1,8 m/s) tidak mengubah tingkat.

*Naskah:* Setiap 5 menit Raspberry Pi menilai setiap zona dari rata-rata pembacaan yang valid. Mulai hari ke-21 indikator termalnya THI dengan kelas daerah tropis lembap; sebelum hari ke-21 yang dinilai adalah selisih suhu terhadap suhu target T* dari tabel Ross menurut bobot sampel terbaru dan kelembapan. NH3 dan CO2 dinilai dengan batas Ross dan aturan Uni Eropa. Tingkat zona naik setelah dua jendela berturut-turut dan turun setelah tiga, untuk mengurangi alarm palsu, dan zona terburuk menentukan tingkat kandang. Bila NH3 berada dalam galat sensor dari batas kelas, pemberitahuan meminta pengecekan dengan kertas indikator. THVI dan pemeriksaan angin rendah hanya catatan. Perlu diketahui: kelas THI berasal dari studi ayam petelur, dan semua batas ini akan dikalibrasi di lapangan.

## Slide 6: Tugas pertama menurut penyebab

- 05 · Kemungkinan penyebab dan tugas
| Penyebab | Kemungkinan penyebab | Tugas, berurutan (Sedang; Berat) | Sumber |
|---|---|---|---|
| Panas (THI, ≥ hari 21) | AIRF aliran udara rendah · HUMH panas lembap · COOL pendinginan kurang | FANS naikkan tahap kipas. Berat: + PADS jalankan cooling pad*, PADC cek pompa pad† | Medion; Ross hlm. 13 |
| Terlalu dingin vs. T* | HTRC pemanas kurang atau udara dingin | CHBH cek anak ayam, HEAT cek pemanas, MVCK cek ventilasi minimum. Berat: HEAT lebih dulu | Ross hlm. 13, 30, 33 |
| Terlalu hangat vs. T* | SETP set point di atas target | CHBH, MVCK. Berat: + HTSP turunkan set point brooding (inferensi perancang, tanpa sumber) | Ross hlm. 30, 33 |
| NH₃ | WETL litter basah (RH ≥ 70%) · LITQ kondisi litter | MVUP naikkan ventilasi minimum, LITC uji genggam litter, cek tempat minum. Berat: + LITR ganti litter | UGA Bul. 1267; Ross hlm. 13 |
| CO₂ | VENT ventilasi kurang | AIRQ ukur kualitas udara, sesuaikan ventilasi | Ross hlm. 33 |
| Angin rendah (≥ minggu 4) | AIRF aliran udara rendah | FANB cek sabuk kipas, bersihkan kipas; INLT atur bukaan inlet | Medion |

- Sedang: tugas pencegahan; Berat: tugas perbaikan. * Pad hanya setelah tahap kipas dinaikkan, bila > 28 °C, RH ≤ 75% dan umur > 14 hari. † Bila angin rendah, FANB sebelum PADC.

*Naskah:* Bersama setiap penilaian Sedang atau Berat, sistem memberi satu kemungkinan penyebab dan paling banyak tiga tugas dari katalog versi 2026-10-v2. Pada tingkat Sedang tugasnya pencegahan, pada tingkat Berat perbaikan. Untuk panas, kemungkinan penyebabnya AIRF bila angin rendah, HUMH bila kelembapan di atas 75 persen, selain itu COOL. Untuk NH3, WETL bila kelembapan 70 persen atau lebih, selain itu LITQ. Setiap tugas menyebut sumbernya: panduan Ross, buletin penyuluhan University of Georgia, dan panduan closed house Medion. Satu tugas, menurunkan set point brooding, tidak ada sumbernya dan ditandai sebagai inferensi perancang. Di Bagian B formulir, Bapak/Ibu akan menilai daftar seperti ini untuk tujuh kondisi.

## Slide 7: Seperti apa peringatan Berat

- 06 · Contoh dan aturan pengaman
- BERAT di zona 1: termal
- Kemungkinan penyebab AIRF: aliran udara rendah (kipas, sabuk atau inlet)
- Tugas perbaikan: / 1. FANS Naikkan tahap kipas untuk menambah kecepatan angin [Medion] / 2. FANB Periksa sabuk kipas, bersihkan kipas [Medion] / 3. INLT Atur bukaan inlet sesuai target kecepatan angin [Medion]
- Catatan: cooling pad ditahan, RH 80% > 75%
- Dari uji emulasi: 34 °C, RH 80%, angin 1,5 m/s, umur 30 hari. Diterjemahkan; sistem menulis dalam bahasa Inggris.
- Kemungkinan penyebab adalah petunjuk berbasis aturan, bukan diagnosis.
- Paling banyak tiga tugas, diambil dari setiap indikator yang bermasalah; cek sebelum tindakan.
- Cooling pad hanya setelah tahap kipas dinaikkan, bila suhu > 28 °C, RH ≤ 75% dan umur > 14 hari.
- Sebelum hari ke-21 tidak ada tugas kipas atau pad: angin setinggi anak ayam harus < 0,15 m/s.
- Tugas hanya saran; controller kandang tetap mengendalikan peralatan.
- Peringatan dan pemberitahuan muncul di lokasi, juga tanpa internet.

*Naskah:* Ini contoh peringatan Berat dari uji emulasi, diterjemahkan ke bahasa Indonesia. Kondisinya 34 derajat, kelembapan 80 persen, angin 1,5 meter per detik, ayam umur 30 hari. Kemungkinan penyebabnya aliran udara rendah, dan ada tiga tugas perbaikan dengan sumbernya. Cooling pad ditahan karena kelembapan di atas 75 persen. Aturan pengamannya: kemungkinan penyebab hanya petunjuk, bukan diagnosis; tugas dimulai dengan pemeriksaan; cooling pad hanya dengan syarat suhu, kelembapan dan umur; sebelum hari ke-21 tidak ada tugas kipas atau pad. Tugas hanya saran, controller kandang tetap mengendalikan peralatan.

## Slide 8: Disimpan sekali; eskalasi pada episode Berat ke-3

- 07 · Bagian SAP
- Episode 1
- Episode 2
- Episode 3
- Episode Berat di satu zona dalam 24 jam, dihitung sejak notifikasi terakhir (ilustrasi)
- Satu notifikasi PM
- di functional location kandang, dengan tugas dari penilaian pemicu
- **1 · Disimpan sekali:** Setiap penilaian punya ID unik (flock, kandang, awal jendela). Kiriman ulang dikenali sebagai duplikat; data tertunda menunggu di outbox.
- **2 · Eskalasi:** Episode Berat ke-3 di satu zona dalam 24 jam, dihitung sejak notifikasi terakhir, membuka satu notifikasi PM.
- **3 · Isi notifikasi:** Teks singkat: zona, kemungkinan penyebab dan penyebab. Tugas dari penilaian pemicu menjadi tugas notifikasi.
- **4 · Penyelesaian:** Staf menandai tugas selesai di SAP PM; bila staf tidak punya akses SAP, kantor farm yang mencatat. Tanpa PM, eskalasi hanya dicatat di log.
- Teknis: middleware REST → function module Z_BRL_STRESS_SAVE (RFC) melalui SOAP/HTTPS sebagai user teknis · tabel ZBRL_STRESS dan ZBRL_NOTIF; PM: QMEL, QMSM · SAP ECC 6.0

*Naskah:* Jalur b berakhir di SAP ECC 6.0. Setiap penilaian 5 menit punya ID unik dari flock, kandang dan awal jendela, sehingga kiriman ulang setelah gangguan jaringan dikenali sebagai duplikat dan tidak tercatat dua kali; selama jaringan putus, data menunggu di outbox. Episode Berat dimulai saat zona menjadi Berat. Episode Berat ketiga di satu zona dalam 24 jam, dihitung sejak notifikasi terakhir, membuka satu notifikasi Plant Maintenance pada functional location kandang, dengan tugas dari penilaian pemicu. Staf menandai tugas selesai di SAP PM, atau kantor farm yang mencatat bila staf tidak punya akses SAP. Bila farm tidak memakai PM, eskalasi hanya dicatat di log dan penyelesaian tugas tidak terekam. Untuk pakar SAP: semua logika ada di satu function module dan satu report, yang juga tersedia di S/4HANA.

## Slide 9: Setiap pagi: laporan per kandang untuk manajer farm

- 08 · Laporan harian
- **Data:** Jendela yang diterima dibanding yang diharapkan; celah data.
- **Kondisi:** Jumlah jendela per tingkat, tingkat terburuk per zona, nilai puncak.
- **Kemungkinan penyebab:** Ditandai berulang bila muncul di ≥ 2 notifikasi atau ≥ 3 episode Berat.
- **Pemeriksaan notifikasi:** Tiap tugas: selesai, terlambat (> 24 jam) atau belum; bila selesai, apakah kembali Normal dalam 3 jendela.
- Contoh isi laporan (diterjemahkan)
- Data: 35 jendela, tanpa celah / Episode Berat zona 1: 3 / Notifikasi PM: 1 (zona 1, AIRF) / FANS selesai (kantor farm) → Normal / FANB selesai (kantor farm) → Normal / INLT selesai (kantor farm) → Normal / Berulang: AIRF aliran udara rendah
- Dari uji loop tertutup dengan sensor emulasi; waktu dipadatkan menjadi jendela 5 detik dan kantor farm diperankan oleh skrip. Bukan data kandang.

*Naskah:* Setiap pagi sebuah job latar di SAP membuat laporan per kandang untuk manajer farm. Isinya empat bagian: kelengkapan data, kondisi, kemungkinan penyebab dengan tanda bila berulang, dan pemeriksaan notifikasi, yaitu status setiap tugas dan apakah kondisi kembali Normal setelah tugas selesai. Tugas yang lewat 24 jam, satu hari kerja, ditandai terlambat. Di kanan ada ringkasan isi laporan dari uji loop tertutup: tiga episode panas, satu notifikasi, tiga tugas yang diselesaikan, kondisi kembali Normal, dan AIRF ditandai berulang. Ini uji emulasi dengan waktu dipadatkan, bukan data kandang.

## Slide 10: Yang kami minta setelah pengarahan ini

- 09 · Formulir penilaian
- **Bagian A · 20 butir:** Aturan: dari tidak sesuai sampai sesuai tanpa revisi. Pernyataan: dari sangat tidak setuju sampai sangat setuju. TD bila di luar bidang Anda.
- **Bagian B · 9 kondisi:** Apakah tingkatnya tepat, kemungkinan penyebabnya masuk akal, dan urutan tugasnya layak sebagai langkah pertama.
- **Hanya angka 1–5:** Tidak ada pertanyaan terbuka. Formulir anonim: tanpa nama, kode atau tanggal.
- Status rancangan
- Diuji dengan sensor emulasi dan SAP tiruan (mock); belum dijalankan di kandang atau di sistem SAP. Kami justru mencari kelemahan rancangan: nilai rendah sama bergunanya dengan nilai tinggi.

*Naskah:* Itu seluruh rancangannya. Sekarang mohon isi Bagian A dan B formulir, sekitar 20 menit; saya tidak akan melihat formulir selama Bapak/Ibu mengisinya. Semua jawaban berupa angka 1 sampai 5. Bagian A berisi 20 butir: tujuh aturan dinilai dari tidak sesuai sampai sesuai tanpa revisi, dan sisanya dinilai dari sangat tidak setuju sampai sangat setuju. Pilih TD bila suatu butir di luar bidang Bapak/Ibu; kolom Bidang membantu. Bagian B berisi sembilan kondisi zona nyata: untuk setiap kondisi, nilailah apakah tingkat dari sistem tepat, apakah kemungkinan penyebabnya masuk akal, dan apakah urutan tugasnya layak sebagai langkah pertama; untuk dua kondisi Normal, hanya tingkatnya. Rancangan ini baru diuji dengan sensor emulasi dan SAP tiruan, belum di kandang atau di sistem SAP. Kami justru mencari kelemahannya: nilai rendah sama bergunanya dengan nilai tinggi. Saya dapat menjawab pertanyaan faktual, tetapi tidak akan membela rancangannya.
