# VisionDoctor 本地 Demo 数据

运行以下命令会使用固定随机种子 `20261016` 在本目录生成 `visiondoctor_demo.zip`：

```powershell
python scripts/generate_demo_dataset.py
```

数据完全由本地脚本合成，不下载或引用互联网素材。ZIP 使用 `dataset/train|val|test/images|labels` 结构，并特意包含可被安全忽略的额外说明文件。它包含正常样本、缺失/空/格式错误标签、非法类别、越界框、极小框、损坏/模糊/过暗/过亮/低分辨率图片、完全重复、近似重复和类别失衡。生成器固定文件顺序、ZIP 时间戳和权限元数据；相同环境下重复生成的 ZIP 字节一致。

运行完整无 UI 冒烟测试：

```powershell
python scripts/smoke_test.py
```

生成的 ZIP 是可随时重建的演示产物，不包含真实用户数据。核心 Pipeline 不需要 API Key、数据库、网络或 Streamlit。

启动界面后，可将生成的 ZIP 上传到 Upload 标签页完成四个页面的演示：

```powershell
python -m streamlit run app.py --server.headless true
```

`visiondoctor_demo.zip` 已被 `.gitignore` 忽略，不应提交到代码仓库。提交前的人工演示应依次核对 Dashboard、Issue Explorer、AI Doctor & Report，以及 JSON/HTML 下载。
