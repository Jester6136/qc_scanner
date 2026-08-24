<claude-mem-context>
# Memory Context

# [qc_scanner] recent context, 2026-08-21 8:42am GMT+7

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 27 obs (10,462t read) | 1,348,651t work | 99% savings

### Aug 20, 2026
139 9:35a 🔵 qc_scanner project documentation structure mapped
140 " 🔵 qc_scanner: document scanning QC pipeline — full system overview
141 " 🔵 qc_scanner open issues: OPS-3, PKG-5/6, QC-23, QUAL-3/4/5, SPD-8, QC-18b, QC-24
142 " 🔵 DocAligner chosen as default detector over rembg after SmartDoc 2015 benchmark
143 " 🔵 QC-22 fix: CONTENT_OUTSIDE_CROP requires three-gate check to avoid 70% false alarm rate
144 " 🔵 qc_scanner algorithm: full processing pipeline with fallback chain and QC metrics
S62 Continue — user asked Claude to continue from where it left off; session proceeded to run qc-scanner on real customer GCN (sổ đỏ) images and analyze why one fails (Aug 20, 9:37 AM)
S61 Đọc hiểu tài liệu dự án qc_scanner — tổng quan kiến trúc, thuật toán, issues, và roadmap (Aug 20, 9:37 AM)
145 9:38a 🔵 qc_scanner not installed in default Python environment
146 " 🔵 pypdfium2 version conflict when installing qc_scanner into base conda env
147 " 🔵 Customer input files are GCN (sổ đỏ) documents: 4 JPGs + 2 PDFs
148 9:43a 🔵 DocAligner model missing from server — downloaded via qc-scanner-fetch-models
149 " 🔵 qc-scanner pass verdict on real GCN JPG with full metrics output
150 " 🔵 qc_scanner results on 4 real GCN JPG images: 2 pass, 1 warn, 1 fail
151 9:44a 🔵 config.py threshold calibration details with embedded measurement rationale
152 " 🔵 gcn_1784692493739.jpg fail analysis: CONTENT_CLIPPED with border_ink_ratio=0.605
153 9:59a 🔵 _content_reasons() code path mapped before implementing detector_confidence gate
154 10:00a 🔴 QC-26 committed: CONTENT_CLIPPED downgrade from fail→warn when detector_confidence ≥ 0.90
155 " 🟣 .env file created with auto-generated API key for Docker deployment
156 " 🔵 docker compose build timed out at 120s — build still running in background
157 10:08a 🔵 Docker build completed successfully — image qc-scanner:local built and container running
S63 Build Docker image and auto-generate .env API key — "build docker, tự tạo env key nhé" — full deployment verification completed (Aug 20, 10:10 AM)
169 3:58p ⚖️ GCN Image Quality Filter Logic Adjustment: Skip Cropping for Fullframe Images
170 " 🔵 QC Scanner Project Environment Confirmed at /home/vms2/minhld/qc_scanner
171 " 🔵 QC Scanner API Returns Raw Binary Image Instead of JSON for GCN Test
173 " ⚖️ GCN Image Validation Logic Revised: Fullframe Skip + Partial Coverage Filter
172 3:59p 🔵 QC Scanner Available Both as Local CLI and Docker Service
174 4:03p 🔵 qc-scanner CLI: Key Flags for Fullframe GCN Image Handling
175 " 🔵 QC Scanner API on Port 5051 Returns Binary PNG, Not JSON Report
176 4:04p 🔵 QC Scanner Actual Failure Modes: gcn_1783818185332.jpg (WARN) and gcn_1786803896999.jpg (FAIL)

Access 1349k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>