function timestamp() {
    return new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z").replace("T", "-");
}

export function downloadCredentialBundle(bundle) {
    const content = `${JSON.stringify(bundle, null, 2)}\n`;
    const url = URL.createObjectURL(new Blob([content], { type: "application/json;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `csn2api-cookies-${timestamp()}.json`;
    link.click();
    URL.revokeObjectURL(url);
}

export async function readCredentialBundleFile(file) {
    if (!(file instanceof File)) throw new Error("请选择 Cookie JSON 或 TXT 文件");
    try {
        return JSON.parse(await file.text());
    } catch (_error) {
        throw new Error("Cookie 文件不是有效 JSON");
    }
}
