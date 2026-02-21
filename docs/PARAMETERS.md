# 3D Slicer Pro – パラメーター仕様書

> 更新: 2026-02-21 (Rev 2 – プリセットシステム追加、OpenGL修正)

---

## 実装状況サマリー

| カテゴリ | 実装済み | 未実装 |
|----------|----------|--------|
| OpenGL 3Dプレビュー | ✅ QSurfaceFormat順序修正済み | — |
| プリセット保存/読み込み | ✅ ビルトイン9種 + ユーザー保存 | — |
| レイヤー / 押出幅 | ✅ | — |
| ウォール | ✅ | seam実処理 (seam_position はUI反映済み、アルゴリズム未接続) |
| インフィル | ✅ | infill_angle は UI/設定のみ (slicer側回転は未実装) |
| トップ/ボトム | ✅ | — |
| リトラクション | ✅ 全パラメーター | — |
| Z-hop | ✅ gcode生成済み | — |
| 速度 (部位別) | ✅ outer/inner/top-bottom/infill/bridge | — |
| 最小レイヤー時間 | UI ✅ | gcode側の速度制限は未実装 |
| サポート | UI ✅ / 基本生成 ✅ | interface layers / z-dist / xy-dist は未接続 |
| ファン (キックイン層/第1層速度) | ✅ | — |
| 第1層温度 | ✅ | — |

---

## パラメーター詳細

### Print タブ

| パラメーター | 型 | デフォルト | 範囲 | 説明 |
|-------------|-----|-----------|------|------|
| `layer_height` | float | 0.20 mm | 0.05 – 0.50 | 通常レイヤー高さ |
| `first_layer_height` | float | 0.30 mm | 0.10 – 0.80 | 第1レイヤー高さ（ベッド密着用に厚め） |
| `wall_count` | int | 3 | 1 – 10 | 外周壁の数 |
| `outer_before_inner` | bool | false | — | 外壁を内壁より先に印刷 |
| `infill_density` | float | 20 % | 0 – 100 | インフィル充填率 |
| `infill_pattern` | enum | grid | grid / lines / honeycomb | インフィルパターン |
| `infill_angle` | float | 45 ° | 0 – 90 | インフィル基準角度 |
| `top_layers` | int | 4 | 0 – 20 | 上面ソリッド層数 |
| `bottom_layers` | int | 4 | 0 – 20 | 底面ソリッド層数 |
| `brim_enabled` | bool | false | — | ブリム（剥がれ防止裾）有効 |
| `brim_width` | float | 8.0 mm | 1.0 – 30.0 | ブリム幅 |

---

### Quality タブ

| パラメーター | 型 | デフォルト | 範囲 | 説明 |
|-------------|-----|-----------|------|------|
| `line_width_pct` | float | 100 % | 70 – 150 | ノズル径に対するライン幅の割合 |
| `line_width` | float | 0.40 mm | — | ノズル径 × line_width_pct/100 で自動計算 |
| `seam_position` | enum | back | back / random / sharpest | Zシーム位置 |
| `infill_overlap` | float | 10 % | 0 – 50 | インフィルが外周に重なる割合 |
| `skin_overlap` | float | 5 % | 0 – 50 | 上下面が外周に重なる割合 |
| `retraction_enabled` | bool | true | — | リトラクション有効 |
| `retraction_distance` | float | 5.0 mm | 0 – 15 | リトラクション引き量 |
| `retraction_speed` | float | 45 mm/s | 5 – 120 | リトラクション速度 |
| `retraction_min_distance` | float | 1.5 mm | 0 – 10 | この距離未満の移動はリトラクションしない |
| `retraction_extra_prime` | float | 0.0 mm | 0 – 2.0 | リトラクション解除後の余分押し出し量 |
| `retraction_z_hop` | float | 0.0 mm | 0 – 2.0 | 移動時のZ方向リフト（0=無効） |

---

### Speed タブ

| パラメーター | 型 | デフォルト | 範囲 | 説明 |
|-------------|-----|-----------|------|------|
| `outer_perimeter_speed` | float | 40 mm/s | 5 – 300 | 外壁速度（表面品質に直結）|
| `print_speed` | float | 60 mm/s | 5 – 300 | 内壁速度（一般速度） |
| `top_bottom_speed` | float | 40 mm/s | 5 – 300 | 上下面ソリッド速度 |
| `infill_speed` | float | 80 mm/s | 5 – 500 | インフィル速度 |
| `bridge_speed` | float | 25 mm/s | 5 – 200 | ブリッジ（空中渡り）速度 |
| `first_layer_speed` | float | 25 mm/s | 5 – 100 | 第1レイヤー全体速度 |
| `travel_speed` | float | 200 mm/s | 20 – 500 | 空移動速度 |
| `min_layer_time` | float | 5 s | 0 – 60 | 最小レイヤー時間（冷却確保） |

> **Easythreed K9 推奨**: outer=18, inner=30, infill=36, travel=60 mm/s

---

### Support タブ

| パラメーター | 型 | デフォルト | 範囲 | 説明 |
|-------------|-----|-----------|------|------|
| `support_enabled` | bool | false | — | サポート有効 |
| `support_threshold` | float | 45 ° | 20 – 80 | オーバーハング判定角度 |
| `support_pattern` | enum | lines | lines / grid / zigzag | サポートパターン |
| `support_density` | float | 15 % | 5 – 50 | サポート密度 |
| `support_z_distance` | float | 0.20 mm | 0 – 2.0 | サポート上下のギャップ |
| `support_xy_distance` | float | 0.70 mm | 0 – 3.0 | サポート横のギャップ |
| `support_interface_enabled` | bool | true | — | インターフェース層有効 |
| `support_interface_layers` | int | 2 | 1 – 8 | インターフェース層数 |

---

### Temp / Fan タブ

| パラメーター | 型 | デフォルト | 範囲 | 説明 |
|-------------|-----|-----------|------|------|
| `print_temp` | int | 210 °C | 150 – 310 | 通常印刷温度 |
| `print_temp_first_layer` | int | 215 °C | 150 – 310 | 第1レイヤー温度（密着向上） |
| `bed_temp` | int | 60 °C | 0 – 150 | ベッド温度（ヒートベッドなし機種では0固定） |
| `fan_speed` | int | 100 % | 0 – 100 | 通常ファン速度 |
| `fan_first_layer` | int | 0 % | 0 – 100 | 第1レイヤーファン速度（通常0） |
| `fan_kick_in_layer` | int | 2 | 1 – 20 | ファン開始レイヤー番号 |

---

## Easythreed K9 設定ガイド

**機体制約**
- 最大印刷速度: 40 mm/s
- 造形サイズ: 100 × 100 × 100 mm
- ヒートベッドなし → ベッド温度 0°C（自動無効化）
- リトラクション: 6.5 mm（Cura K9サンプル実測値）

**推奨設定**

```
レイヤー高さ:   0.2 – 0.3 mm
外壁速度:       20 mm/s
内壁速度:       30 mm/s
インフィル速度: 36 mm/s
第1層速度:      15 mm/s
リトラクション: 6.5 mm @ 25 mm/s
温度 (PLA):     200°C (第1層 205°C)
ファン:         第3レイヤーから 100%
```

---

## プリセットシステム

### ビルトインプリセット（読み取り専用）
| プリセット名 | 用途 |
|-------------|------|
| Draft (0.3mm, 10%, Fast) | 速度優先、品質低め |
| Normal Quality (0.2mm, 20%) | 汎用標準設定 |
| High Quality (0.15mm, 30%) | 品質優先、低速 |
| Strong (0.2mm, 50%, Honeycomb) | 強度優先、ハニカムインフィル |
| With Support (Normal) | サポートあり標準設定 |
| K9 – Draft | Easythreed K9専用・速度優先 |
| K9 – Normal | Easythreed K9専用・標準 |
| K9 – Quality | Easythreed K9専用・品質優先 |
| PETG Normal | PETG向け設定 |

### ユーザープリセットの保存場所
```
profiles/presets/{プリセット名}.json
```

### プリセットJSONフォーマット
SliceSettingsの全フィールド + メタデータ：
```json
{
  "_printer": "Easythreed K9",
  "_material": "PLA",
  "layer_height": 0.2,
  "infill_density": 20,
  ... (全パラメーター)
}
```

---

## 既知の課題 / TODO

| 優先度 | 項目 | 状態 |
|--------|------|------|
| 高 | `seam_position` をスライサーアルゴリズムに接続 | 未実装 |
| 高 | `infill_angle` をインフィル生成に接続 | 未実装 |
| 中 | `min_layer_time` による速度自動制限 | UI のみ |
| 中 | `support_z_distance` / `support_xy_distance` をサポート生成に接続 | UI のみ |
| 中 | `support_interface_layers` をサポート生成に接続 | UI のみ |
| 低 | `bridge_speed` の自動ブリッジ検出 | 未実装 |
| 低 | ジャイロイドインフィルパターン追加 | 未実装 |

---

## G-code 出力仕様

生成されるG-codeのコメント形式はCura互換：
```gcode
; TYPE:WALL-OUTER   ← 外壁
; TYPE:WALL-INNER   ← 内壁
; TYPE:SKIN         ← 上下面
; TYPE:FILL         ← インフィル
; TYPE:SUPPORT      ← サポート
; TYPE:BRIM         ← ブリム
```

E値計算式：
```
E = 距離 × ライン幅 × レイヤー高さ / (π × (フィラメント径/2)²)
```
