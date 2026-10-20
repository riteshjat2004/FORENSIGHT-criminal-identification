import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import styles from "./Results.module.css";

function dataUrlToFile(dataUrl, filename) {
  try {
    const [meta, b64] = dataUrl.split(",");
    const mime = meta.match(/data:(.*);base64/)?.[1] || "image/png";
    const bin = atob(b64);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    const blob = new Blob([buf], { type: mime });
    return new File([blob], filename, { type: mime });
  } catch {
    return new File([], filename, { type: "image/jpeg" });
  }
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
        canvas.width = Math.max(1, width);
        canvas.height = Math.max(1, height);
        const ctx = canvas.getContext("2d");

        // Fill clean white background so transparent PNGs/sketches never turn pitch black in JPEG
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
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
  const lastSearchKeyRef = useRef(null);

  useEffect(() => {
    if (location.state?.generatedImageUrl) {
      try {
        sessionStorage.setItem("generatedImageUrl", location.state.generatedImageUrl);
      } catch (err) {
        console.warn("sessionStorage quota exceeded:", err);
      }
      setGeneratedImageUrl(location.state.generatedImageUrl);
    }
    if (location.state?.gender) {
      try {
        sessionStorage.setItem("generatedGender", location.state.gender);
      } catch (err) {
        console.warn("sessionStorage quota exceeded:", err);
      }
      setGender(location.state.gender);
    }
  }, [location.state]);

  const runSearch = useCallback(
    async (overrideImgUrl) => {
      const activeUrl = overrideImgUrl || generatedImageUrl;

      const token = localStorage.getItem("token");
      if (!token) {
        alert("Please login first");
        window.location.href = "/login";
        return;
      }

      if (!activeUrl) {
        alert("Please generate or select an image first");
        return;
      }

      setLoading(true);

      try {
        const imageFile = await prepareOptimizedImageFile(
          activeUrl,
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
          if (res.status === 401) {
            alert("Your session has expired. Please login again.");
            localStorage.removeItem("token");
            localStorage.removeItem("role");
            window.dispatchEvent(new Event("authchange"));
            window.location.href = "/login";
            return;
          }
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

  // Automatically trigger search when a new search state arrives (including timestamp from header)
  useEffect(() => {
    const currentTargetUrl = location.state?.generatedImageUrl || generatedImageUrl;
    const currentSearchKey = location.state?.searchTimestamp
      ? `${currentTargetUrl}-${location.state.searchTimestamp}`
      : currentTargetUrl;

    if (currentTargetUrl && currentSearchKey !== lastSearchKeyRef.current) {
      lastSearchKeyRef.current = currentSearchKey;
      runSearch(currentTargetUrl);
    }
  }, [location.state, generatedImageUrl, runSearch]);

  return (
    <div className={styles.page}>
      <div className={styles.layout}>
        <section className={styles.left}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Query Face Image</h2>

            {generatedImageUrl ? (
              <img className={styles.generatedImg} src={generatedImageUrl} alt="Query Face" />
            ) : (
              <p className={styles.muted}>No face image selected yet. Use &ldquo;Search Image&rdquo; above or generate one in the editor.</p>
            )}
          </div>
        </section>

        <section className={styles.right}>
          <div className={styles.card}>
            <h2 className={styles.cardTitle}>Matched Faces</h2>

            <form className={styles.searchForm} onSubmit={(e) => { e.preventDefault(); runSearch(); }}>
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
                    {generatedImageUrl ? "No matches found above threshold." : "Generate or search an image to find matches."}
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
