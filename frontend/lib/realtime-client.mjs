export async function uploadEntry(audioBlob) {
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");

    const response = await fetch("http://localhost:8000/entries", {
        method: "POST",
        body: formData
    });

    if (!response.ok) {
        throw new Error("Upload failed: " + response.statusText);
    }

    return await response.json();
}
