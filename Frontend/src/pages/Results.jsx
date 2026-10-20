import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import styles from "./Results.module.css";

function dataUrlToFile(dataUrl, filename) {
  const [meta, b64] = dataUrl.split(",");
  const mime = meta.match(/data:(.*);base64/)?.[1] || "image/png";
  const bin = atob(b64);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  const blob = new Blob([buf], { type: mime });
  return new File([blob], filename, { type: mime });
}

async function prepareOptimizedImageFile(dataUrl, filename) {
  return new Promise((resolve) => {
    try {
      const img = new Image();
      img.onload = () => {
        const MAX_DIM = 640;
        let { width, height } = img;
        if (width > MAX_DIM || height > MAX_DIM) {
          if (width > height) {
            height = Math.round((height * MAX_DIM) / width);
            width = MAX_DIM;
          } else {
            width = Math.round((width * MAX_DIM) / height);
            height = MAX_DIM;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);
        canvas.toBlob(
          (blob) => {
            if (blob) {
              resolve(new File([blob], filename, { type: "image/jpeg" }));
            } else {
              resolve(dataUrlToFile(dataUrl, filename));
            }
          },
          "image/jpeg",
          0.92
        );
      };
      img.onerror = () => resolve(dataUrlToFile(dataUrl, filename));
      img.src = dataUrl;
    } catch {
      resolve(dataUrlToFile(dataUrl, filename));
    }
  });
}

export default function Results() {
  const location = useLocation();
  const API_BASE = useMemo(() => {
    const raw = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE || "http://localhost:8000";
    return raw.replace(/\/+$/, "");
  }, []);

  const [generatedImageUrl, setGeneratedImageUrl] = useState(() => {
    return (
      location.state?.generatedImageUrl ||
      sessionStorage.getItem("generatedImageUrl") ||
      null
    );
  });

  const [gender, setGender] = useState(() => {
    return location.state?.gender || sessionStorage.getItem("generatedGender") || "Any";
  });

  const [loading, setLoading] = useState(false);
  const [matches, setMatches] = useState([]);
  const [autoSearched, setAutoSearched] = useState(false);

  useEffect(() => {
    if (location.state?.generatedImageUrl) {
      sessionStorage.setItem("generatedImageUrl", location.state.generatedImageUrl);
      setGeneratedImageUrl(location.state.generatedImageUrl);
    }
    if (location.state?.gender) {
      sessionStorage.setItem("generatedGender", location.state.gender);
      setGender(location.state.gender);
    }
  }, [location.state]);

  const runSearch = useCallback(
    async (e) => {
      e?.preventDefault?.();

      const token = localStorage.getItem("token");
      if (!token) {
        alert("Please login first");
        return;
      }

      if (!generatedImageUrl) {
        alert("Please generate or select an image first");
        return;
      }

      setLoading(true);

      try {
        const imageFile = await prepareOptimizedImageFile(
          generatedImageUrl,
          `search-${Date.now()}.jpg`
        );

        const formData = new FormData();
        formData.append("image", imageFile);
        if (gender && gender !== "Any") formData.append("sex_filter", gender);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 45000);

        const res = await fetch(`${API_BASE}/api/upload`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        let data = {};
        try {
          data = await res.json();
        } catch {
          data = {};
        }

        if (!res.ok) {
          alert(data.error || data.message || `Search failed (HTTP ${res.status})`);
          setMatches([]);
          return;
        }

        const sorted = (data.matches || []).sort((a, b) => b.score - a.score);
        setMatches(sorted);
      } catch (err) {
        console.error("Search request error:", err);
        if (err.name === "AbortError") {
          alert("Search timed out. The server is busy, please try again in a moment.");
        } else {
          alert(err?.message || "Server error: could not connect to server");
        }
        setMatches([]);
      } finally {
        setLoading(false);
      }
    },
    [generatedImageUrl, gender, API_BASE],
  );

  useEffect(() => {
    if (!autoSearched && generatedImageUrl) {
      setAutoSearched(true);
      runSearch();
    }
  }, [autoSearched, generatedImageUrl, runSearch]);

  return (
    <div className={styles.page}>
      <div className={styles.layout}>
        <section className={styles.left}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Generated Image</h2>

            {generatedImageUrl ? (
              <img className={styles.generatedImg} src={generatedImageUrl} alt="Generated" />
            ) : (
              <p className={styles.muted}>No generated image yet.</p>
            )}
          </div>
        </section>

        <section className={styles.right}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Matched Faces</h2>

            <form className={styles.searchForm} onSubmit={runSearch}>
              <button className={styles.primaryBtn} type="submit" disabled={loading}>
                {loading ? "Searching..." : "Search"}
              </button>
            </form>

            <div className={styles.resultsScroll}>
              {matches.length > 0 ? (
               <div className={styles.resultsGrid}>
  {matches.slice(0, 12).map((m, i) => (
    <div
      key={`${m.name}-${i}`}
      className={i === 0 ? styles.resultCardBest : styles.resultCard}
    >
      {m.imageURL && (
        <div className={styles.imgWrapper}>
          <img
            className={styles.resultImg}
            src={m.imageURL}
            alt={m.name || "match"}
          />
        </div>
      )}

      <p className={styles.matchLine}>
        Match:{" "}
        {typeof m.score === "number"
          ? `${(m.score * 100).toFixed(1)}%`
          : "-"}
      </p>

      <p className={styles.nameLine}>{m.name}</p>

      {m.age != null && <p className={styles.metaLine}>Age: {m.age}</p>}
      {m.sex && <p className={styles.metaLine}>Sex: {m.sex}</p>}
      {m.crime && <p className={styles.metaLine}>Crime: {m.crime}</p>}
      {m.status && <p className={styles.metaLine}>Status: {m.status}</p>}
    </div>
  ))}
</div>
              ) : (
                !loading && (
                  <p className={styles.muted}>
                    {generatedImageUrl ? "No matches yet." : "Generate an image to search."}
                  </p>
                )
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
