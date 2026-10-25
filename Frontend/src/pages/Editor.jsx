import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import AssetPanel from "../components/AssetPanel.jsx";
import CanvasArea from "../components/CanvasArea.jsx";
import LayersPanel from "../components/LayersPanel.jsx";
import Toast from "../components/Toast.jsx";
import { useCanvas } from "../hooks/useCanvas.js";
import { useToast } from "../hooks/useToast.js";
import styles from "./Editor.module.css";

export default function Editor() {
  const { toasts, showToast } = useToast();
  const navigate = useNavigate();

  const API_BASE = useMemo(() => {
    const raw = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";
    return raw.replace(/\/+$/, "");
  }, []);
  const token = localStorage.getItem("token");

  const [generatedImageUrl, setGeneratedImageUrl] = useState(null);
  const [gender, setGender] = useState(() => {
    return sessionStorage.getItem("generatedGender") || "Any";
  });
  const [matches, setMatches] = useState([]);
  const [matchLoading, setMatchLoading] = useState(false);
  const [searchAttempted, setSearchAttempted] = useState(false);

  const {
    canvasRef,
    elements,
    selectedElement,
    selectedId,
    addElement,
    deleteSelected,
    bringForward,
    sendBackward,
    setRotation,
    setPositionX,
    setPositionY,
    selectById,
    exportCleanImage,
    downloadImage,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    CANVAS_W,
    CANVAS_H,
  } = useCanvas(showToast);

  // Welcome toast on mount
  useEffect(() => {
    showToast("Welcome to FORENSIGHT! 🎨", "info");
  }, []); // eslint-disable-line

  const dataUrlToBlob = (dataUrl) => {
    const [meta, b64] = dataUrl.split(",");
    const mime = meta.match(/data:(.*);base64/)?.[1] || "image/png";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return new Blob([buf], { type: mime });
  };

  const uploadImageForMatch = async (file) => {
    if (!file) return;
    if (!token) {
      showToast("Please login first", "warning");
      return;
    }

    const formData = new FormData();
    formData.append("image", file);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120000);

    try {
      setMatchLoading(true);
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || data.message || "Upload failed", "warning");
        return;
      }

      const sorted = (data.matches || []).sort((a, b) => b.score - a.score);
      setMatches(sorted);
      setSearchAttempted(true);
      showToast(
        sorted.length ? `Found ${sorted.length} match(es)` : "No matches found",
        sorted.length ? "success" : "info",
      );
    } catch (err) {
      if (err.name === "AbortError") {
        showToast("Search timed out. The server is spinning up, please retry in a moment.", "warning");
      } else {
        showToast("Server error: could not connect to recognition server", "warning");
      }
    } finally {
      clearTimeout(timeoutId);
      setMatchLoading(false);
    }
  };

  const generatePreview = useCallback(() => {
    if (elements.length === 0) {
      showToast("Add some facial elements first!", "warning");
      return;
    }
    const currentGender = gender || "Any";
    const url = exportCleanImage?.() || canvasRef.current?.toDataURL("image/png");
    if (!url) return;
    setGeneratedImageUrl(url);
    setSearchAttempted(false);
    setMatches([]);

    try {
      sessionStorage.setItem("generatedImageUrl", url);
      sessionStorage.setItem("generatedGender", currentGender);
    } catch {
      // ignore storage quota failures
    }

    navigate("/results", {
      state: {
        generatedImageUrl: url,
        gender: currentGender,
        searchTimestamp: Date.now(),
      },
    });
  }, [elements.length, gender, exportCleanImage, canvasRef, showToast, navigate]);

  // Listen to header "Generate Image" button click when already on this editor page
  useEffect(() => {
    const handleHeaderGenerate = () => {
      generatePreview();
    };
    window.addEventListener("forensight:generate-canvas", handleHeaderGenerate);
    return () => {
      window.removeEventListener("forensight:generate-canvas", handleHeaderGenerate);
    };
  }, [generatePreview]);

  const onGenderChange = (nextGender) => {
    const val = nextGender || "Any";
    setGender(val);
    try {
      sessionStorage.setItem("generatedGender", val);
    } catch {
      // ignore storage failures
    }
  };

  const uploadGeneratedForMatch = async () => {
    if (!generatedImageUrl) {
      showToast("Generate the image first", "warning");
      return;
    }
    const blob = dataUrlToBlob(generatedImageUrl);
    const file = new File([blob], `generated-${Date.now()}.png`, {
      type: "image/png",
    });
    await uploadImageForMatch(file);
  };

  const goToUploadForm = () => {
    navigate("/upload");
  };

  return (
    <div className={styles.appWrapper}>
      <div className={styles.layout}>
        <AssetPanel onSelect={addElement} />

        <CanvasArea
          canvasRef={canvasRef}
          selectedElement={selectedElement}
          gender={gender}
          onGenderChange={onGenderChange}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onDelete={deleteSelected}
          onBringForward={bringForward}
          onSendBackward={sendBackward}
          onDownload={downloadImage}
          onGenerate={generatePreview}
          onSearch={uploadGeneratedForMatch}
          onUploadToDatabase={goToUploadForm}
          generatedImageUrl={generatedImageUrl}
          matches={matches}
          searchLoading={matchLoading}
          searchAttempted={searchAttempted}
          onRotate={setRotation}
          onMoveX={setPositionX}
          onMoveY={setPositionY}
          canvasW={CANVAS_W}
          canvasH={CANVAS_H}
        />

        <LayersPanel
          elements={elements}
          selectedId={selectedId}
          onSelect={selectById}
        />
      </div>

      <Toast toasts={toasts} />
    </div>
  );
}
