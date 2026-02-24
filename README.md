# Kasynel_Slicer

Windows 向け FDM 3D プリンタースライサー。STL / OBJ / PLY などの3Dモデルを読み込み、Marlin / Klipper 対応の G-code を生成します。

![Version](https://img.shields.io/badge/Version-v1.0.0-orange)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.4%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## 目次

1. [動作環境](#動作環境)
2. [インストール・起動](#インストール起動)
3. [画面説明](#画面説明)
4. [使い方](#使い方)
5. [設定パラメータ詳細](#設定パラメータ詳細)
6. [プリンタープロファイル](#プリンタープロファイル)
7. [マテリアルプロファイル](#マテリアルプロファイル)
8. [ビルドイン・プリセット](#ビルトインプリセット)
9. [ファイル構成](#ファイル構成)
10. [変更履歴](#変更履歴)

---

## 動作環境

| 項目 | 要件 |
|------|------|
| OS | Windows 10 / 11 (64bit) |
| Python | 3.10 以上 |
| GPU | OpenGL 3.3 Core Profile 対応 |
| RAM | 4GB 以上推奨 |

### Python 依存ライブラリ

```
PyQt6 >= 6.4.0          # GUI フレームワーク
PyOpenGL >= 3.1.7        # 3D ビューポート
PyOpenGL_accelerate      # OpenGL 高速化
numpy >= 1.24.0          # 数値演算
trimesh >= 3.21.0        # メッシュ読込・断面処理
shapely >= 2.0.0         # 2D ポリゴン演算（壁・インフィル）
scipy >= 1.10.0          # 数値計算
networkx >= 3.0          # グラフ演算（trimesh 依存）
```

---

## インストール・起動

### 1. リポジトリのクローン

```bash
git clone https://github.com/Xenoah/Windows_3DP_GcodeSlicer.git
cd Windows_3DP_GcodeSlicer
```

### 2. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 3. 起動

```bash
# バッチファイルで起動（推奨）
run.bat

# または直接実行
python main.py
```

### EXE ビルド（PyInstaller）

```bash
build.bat
# dist/Kasynel_Slicer/ にスタンドアロン EXE が生成される
```

---

## 画面説明

```
┌─────────────────────────────────────────────────────┐
│ File  View  Setting  Help   [Open] [Slice] [Export]  │  ← メニュー / ツールバー
├──────────┬──────────────────────────┬────────────────┤
│          │                          │ Machine        │
│  Models  │                          │  Printer: ...  │
│ ┌──────┐ │     3D Viewport          │  Material: ... │
│ │model │ │    (OpenGL 3.3)          ├────────────────┤
│ │.stl  │ │                          │ Presets        │
│ └──────┘ │  ← 左ドラッグ: 回転      ├────────────────┤
│          │  ← 中ドラッグ: パン      │ Print Quality  │
│  [Add]   │  ← ホイール: ズーム      │ Speed  Support │
│ [Remove] │                          │ Temp/Fan       │
│          ├──────────────────────────┤                │
│          │ Layers: ──●──────── 160  │ [SLICE NOW]    │
└──────────┴──────────────────────────┴────────────────┘
│ Ready - Open a model to start   Layers: -   Est: --  │  ← ステータスバー
└──────────────────────────────────────────────────────┘
```

---

## 使い方

### 基本フロー

1. **モデルを開く**
   - ツールバー「Open」または File → Open Model
   - 対応形式: `.stl` `.obj` `.ply` `.3mf` `.fbx` `.step` `.stp`
   - 複数モデルの同時読込可能（左パネルのリストで管理）

2. **プリンター・マテリアルを選択**
   - 右パネル上部の「Machine」セクションで選択
   - プリンター変更時はベッドサイズが自動反映され、グリッドと造形位置が更新される

3. **スライス設定を調整**
   - 右パネルのタブで各種パラメータを設定
   - 設定変更時は自動でスライス済みデータが破棄される（再スライスが必要）
   - 設定は自動保存される（次回起動時に復元）

4. **スライス実行**
   - 「SLICE NOW」ボタン（バックグラウンドスレッドで実行）
   - 完了後、自動で「Layer Preview」ビューに切り替わる
   - 下部のスライダーでレイヤーを切り替えて確認

5. **G-code エクスポート**
   - 「Export G-code」ボタン または File → Export G-code
   - `.gcode` ファイルとして保存

### カメラ操作

| 操作 | 動作 |
|------|------|
| 左ドラッグ | カメラ回転（軌道カメラ） |
| 中ドラッグ | パン（視点移動） |
| スクロールホイール | ズームイン/アウト |
| `R` キー | カメラリセット |

### ビュー切替

- **3D Model**: ソリッドメッシュ表示
- **Layer Preview**: スライスパスを色分け表示（スライス後に有効）

### レイヤーカラー

| 色 | 種類 |
|----|------|
| オレンジ | 外周（Perimeter） |
| 緑 | インフィル（Infill） |
| シアン | トップ/ボトム（Skin） |
| 黄色 | サポート（Support） |
| ピンク | ブリム（Brim） |

---

## 設定パラメータ詳細

### Print タブ

#### Layer（レイヤー）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Layer height | 0.20 mm | 通常レイヤー高さ |
| First layer height | 0.30 mm | 第1層の高さ（高めにすると密着性向上） |

#### Walls（外壁）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Wall count | 3 | 外壁の層数（多いほど強度向上） |
| Outer wall first | OFF | ON にすると外側から内側へ印刷 |

#### Non-stop / Spiralize（ノンストップ印刷）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| ノンストップ印刷モード | OFF | 花瓶モード。Z上昇と横移動を同時に行い、つなぎ目のない螺旋印刷をする |

> **ノンストップモードの仕様:**
> - ベース層（Bottom layers 枚数分）はソリッドで通常印刷
> - それ以降は外周1本のみ、Z を連続的に上昇させながら印刷
> - インフィル・トップ層・サポートは無視される
> - リトラクションなし（連続押出し）

#### Infill（インフィル）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Infill density | 20% | 充填密度（0%=中空、100%=完全充填） |
| Pattern | grid | `grid`（格子）/ `lines`（直線）/ `honeycomb`（ハニカム） |
| Angle | 45° | インフィルの基準角度（レイヤーごとに90°交互） |

#### Top / Bottom layers

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Top layers | 4 | 上面ソリッド層数 |
| Bottom layers | 4 | 下面ソリッド層数 |

#### Brim（ブリム）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Enable brim | OFF | ブリム（底面の接着補助帯）を有効化 |
| Brim width | 8.0 mm | ブリムの幅 |

---

### Quality タブ

#### Extrusion width

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Line width | 100% | ノズル径に対するライン幅の割合（80〜150%） |

#### Seam position（シーム位置）

| 値 | 説明 |
|----|------|
| `back` | 常にモデル背面にシームを配置 |
| `random` | レイヤーごとにランダム配置 |
| `sharpest` | 最も鋭いコーナーに配置 |

#### Retraction（リトラクション）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Enable retraction | ON | リトラクションの有効/無効 |
| Distance | 5.0 mm | リトラクション量（ボーデン: 4〜7mm、ダイレクト: 0.5〜2mm） |
| Speed | 45 mm/s | リトラクション速度 |
| Min travel | 1.5 mm | これ以下の移動ではリトラクションをスキップ |
| Extra prime | 0.0 mm | デリトラクション後の追加押出し量 |

#### Z-hop

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Z-hop height | 0.0 mm | トラベル移動時のノズル持ち上げ量（0=無効） |

---

### Speed タブ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Outer wall | 40 mm/s | 外周（品質重視） |
| Inner wall | 60 mm/s | 内周 |
| Top/Bottom | 40 mm/s | 上下ソリッド面 |
| Infill | 80 mm/s | 疎インフィル |
| Bridge | 25 mm/s | ブリッジ印刷（架け渡し） |
| First layer | 25 mm/s | 第1層（全フィーチャー共通） |
| Travel | 200 mm/s | 空送り |
| Min layer time | 5 s | 最短レイヤー時間（これより速い場合は減速） |

---

### Support タブ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Enable supports | OFF | サポート構造の有効/無効 |
| Overhang angle | 45° | この角度以上のオーバーハングにサポートを生成 |
| Pattern | lines | `lines` / `grid` / `zigzag` |
| Density | 15% | サポートの充填密度 |
| Z distance | 0.2 mm | モデル上下とサポートの隙間 |
| XY distance | 0.7 mm | モデル側面とサポートの隙間 |
| Interface layers | ON / 2層 | サポートとモデルの接触面に密なインターフェース層を追加 |

---

### Temp/Fan タブ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| Normal temp | 210 °C | 通常印刷温度 |
| First layer temp | 215 °C | 第1層の印刷温度（高めで密着性向上） |
| Bed | 60 °C | ベッド温度（非加熱ベッドは 0） |
| Normal fan speed | 100% | 通常時のパーツ冷却ファン速度 |
| First layer fan | 0% | 第1層のファン速度（通常 OFF） |
| Start fan at layer | 2 | この層からファンを開始 |

---

## プリンタープロファイル

`profiles/printers.json` に定義。⚙ ボタンからGUI で追加・編集可能。

| プリンター | ベッドサイズ | 最大速度 | 備考 |
|-----------|------------|---------|------|
| Bambu Lab X1C | 256×256×256 mm | 500 mm/s | マルチカラー対応 |
| Bambu Lab P1P | 256×256×256 mm | 500 mm/s | |
| Prusa MK4 | 250×210×220 mm | 300 mm/s | |
| Creality Ender-3 | 220×220×250 mm | 150 mm/s | |
| Easythreed K9 | 100×100×100 mm | 40 mm/s | 非加熱ベッド |
| Generic Printer | 220×220×250 mm | 300 mm/s | |

### カスタムプリンター追加

⚙ ボタン → 「+ Add」で新規追加。以下のフィールドを設定:

```json
{
  "bed_size": [220, 220, 250],
  "bed_temp_max": 100,
  "nozzle_diameter": 0.4,
  "filament_diameter": 1.75,
  "max_print_speed": 150,
  "default_print_speed": 60,
  "default_layer_height": 0.2,
  "default_retraction_distance": 5.0,
  "default_retraction_speed": 45,
  "start_gcode": "G28\nG92 E0",
  "end_gcode": "M104 S0\nM140 S0\nM84"
}
```

---

## マテリアルプロファイル

`profiles/materials.json` に定義。

| マテリアル | 印刷温度 | ベッド温度 | ファン | リトラクション |
|-----------|---------|----------|------|--------------|
| PLA | 210 °C | 60 °C | 100% | 5.0 mm |
| PETG | 235 °C | 80 °C | 50% | 6.0 mm |
| ABS | 240 °C | 100 °C | 0% | 5.0 mm |
| TPU | 220 °C | 50 °C | 30% | 2.0 mm |
| ASA | 245 °C | 100 °C | 20% | 5.0 mm |

---

## ビルトインプリセット

右パネル「Presets」から選択して「Load」。ユーザー独自のプリセットも「Save…」で保存可能。

| プリセット名 | 層高 | インフィル | 用途 |
|------------|------|---------|------|
| Draft (0.3mm, 10%, Fast) | 0.3 mm | 10% | 速度優先・試作 |
| Normal Quality (0.2mm, 20%) | 0.2 mm | 20% | 汎用 |
| High Quality (0.15mm, 30%) | 0.15 mm | 30% | 品質優先 |
| Strong (0.2mm, 50%, Honeycomb) | 0.2 mm | 50% | 強度優先 |
| With Support (Normal) | 0.2 mm | 20% | サポート付き |
| K9 – Draft / Normal / Quality | 各種 | 各種 | Easythreed K9 専用 |
| PETG Normal (0.2mm, 20%) | 0.2 mm | 20% | PETG 素材向け |

---

## ファイル構成

```
Windows_3DP_GcodeSlicer/
├── main.py                     # エントリーポイント
├── run.bat                     # 起動スクリプト
├── build.bat                   # EXE ビルドスクリプト
├── requirements.txt            # Python 依存ライブラリ
├── slicer3d.spec               # PyInstaller 設定
│
├── src/
│   ├── core/
│   │   ├── slicer.py           # スライスエンジン（断面生成・パス計算）
│   │   ├── gcode.py            # G-code 生成器
│   │   ├── infill.py           # インフィルパターン（grid/lines/honeycomb）
│   │   ├── support.py          # サポート構造生成
│   │   └── mesh.py             # メッシュコンテナ（trimesh ラッパー）
│   │
│   ├── ui/
│   │   ├── main_window.py      # メインウィンドウ
│   │   ├── viewport.py         # OpenGL 3.3 ビューポート
│   │   ├── settings_panel.py   # 設定パネル（5タブ）
│   │   ├── themes.py           # カラーテーマシステム
│   │   ├── printer_dialog.py   # プリンター設定ダイアログ
│   │   └── layer_slider.py     # レイヤースライダー
│   │
│   └── loaders/
│       └── loader.py           # 汎用ローダー（STL/OBJ/PLY/FBX/STEP）
│
├── profiles/
│   ├── printers.json           # プリンタープロファイル
│   ├── materials.json          # マテリアルプロファイル
│   ├── session.json            # 最終セッション設定（自動生成・Git 管理外）
│   └── presets/                # ユーザープリセット保存先
│
└── sample/
    └── 3DBenchy.stl            # サンプルモデル
```

---

## 変更履歴

### v1.0.0 (2026-02-24)

#### ソフトウェア名称変更
- **「3D Slicer Pro」→「Kasynel_Slicer」** に正式改名
  - 北欧神話の Odin にちなんだ名称
  - 全ソースファイル・G-code ヘッダー・UI 表記を統一

#### 追加
- **カラーテーマシステム** (`src/ui/themes.py`)
  - プリセット 6種: Dark / Darker / Ocean / Solarized Dark / Light / High Contrast
  - カスタムテーマ: 背景・テキスト・アクセントの3色を自由に設定
  - Setting → Theme… メニューから設定、テーマはセッションに自動保存
- **設定のリセット機能**
  - 「↺ Reset」ボタンで全設定をデフォルト値に戻す（確認ダイアログあり）
- **設定ファイルの Import / Export**
  - 「Import…」「Export…」ボタンで設定を JSON ファイルとして保存・読込
- **MITライセンス表示**
  - Help → License… メニューからライセンス全文を確認可能
- **About ダイアログに作者クレジット追加**
  - Developed by Xenoah / Released under the MIT License.

#### 修正
- **カメラ操作の上下・左右反転修正**
  - 左ドラッグ上下（仰角）の方向を反転
  - 中ドラッグ（パン）の左右方向を反転
- **PowerShell 実行ポリシーエラー修正**
  - `run.bat` を `venv\Scripts\python.exe` 直接呼び出し方式に変更（Activate.ps1 不要）

---

### 2026-02-23 (デバッグ・テスト)

#### 修正
- **「View → Toggle Grid」メニューが機能しないバグ修正**
- **プリンタープロファイルに速度デフォルト値を追加**
- **Generic Printer のベッドサイズ修正** (`200×200` → `220×220` mm)
- **SLICE NOW ボタンを起動時に無効化**

---

### 2026-02-23

#### 追加
- **ノンストップ印刷モード（スパイラル/花瓶モード）**
- **セッション自動保存・復元**
- **設定変更でスライスデータを自動破棄**

#### 修正
- **プリンター変更時のベッドサイズ未反映バグ修正**
- **造形サイズオーバーバグ修正**
- **2回目スライスでクラッシュするバグ修正**
- **動作の重さ改善**
- **Git リポジトリの整理**

---

## ライセンス

MIT License — Copyright (c) 2026 Xenoah

---

*このソフトウェアは [Claude Code](https://claude.ai/claude-code) を使用して開発されています。*
