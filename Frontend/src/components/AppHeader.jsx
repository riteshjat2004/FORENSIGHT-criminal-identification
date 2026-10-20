import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import styles from "./AppHeader.module.css";

// Client-side image pre-scaling & optimization to avoid sessionStorage quota crashes (5MB browser limit)
// and prevent sending massive multi-megabyte payloads to the backend.
function resizeImageFileToDataUrl(file, maxDimension = 640) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Failed to read image file"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Invalid or corrupted image"));
      img.onload = () => {
        let { width, height } = img;
        if (width > maxDimension || height > maxDimension) {
          if (width > height) {
            height = Math.round((height * maxDimension) / width);
            width = maxDimension;
          } else {
            width = Math.round((width * maxDimension) / height);
            height = maxDimension;
          }
        }
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, width);
        canvas.height = Math.max(1, height);
        const ctx = canvas.getContext("2d");

        // Paint white background to ensure transparent PNGs don't turn black when converted to JPEG
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);

        const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
        resolve(dataUrl);
      };
      img.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  });
}

export default function AppHeader() {
  const navigate = useNavigate();
  const location = useLocation();

  const [token, setToken] = useState(() => localStorage.getItem("token"));
  const [role, setRole] = useState(() => localStorage.getItem("role"));
  const [isProcessingSearch, setIsProcessingSearch] = useState(false);
  const uploadMatchRef = useRef(null);

  const [searchName, setSearchName] = useState("");
  const [searchSex, setSearchSex] = useState("Any");

  useEffect(() => {
    const sync = () => {
      setToken(localStorage.getItem("token"));
      setRole(localStorage.getItem("role"));
    };
    window.addEventListener("authchange", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("authchange", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  // Sync token state on route navigation
  useEffect(() => {
    setToken(localStorage.getItem("token"));
    setRole(localStorage.getItem("role"));
  }, [location.pathname]);

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    try {
      sessionStorage.removeItem("generatedImageUrl");
      sessionStorage.removeItem("generatedGender");
    } catch {
      // ignore
    }
    window.dispatchEvent(new Event("authchange"));
    navigate("/login");
  };

  const goGenerate = () => {
    if (!token) {
      navigate("/login");
      return;
    }

    if (location.pathname === "/app") {
      // If already in the sketch editor, trigger face generation directly
      window.dispatchEvent(new CustomEvent("forensight:generate-canvas"));
    } else {
      navigate("/app");
    }
  };

  const runMemberSearch = (e) => {
    e?.preventDefault?.();

    if (!token) {
      alert("Please login first");
      return;
    }

    const name = searchName.trim();
    if (!name) {
      return;
    }

    const params = new URLSearchParams();
    params.set("name", name);
    if (searchSex && searchSex !== "Any") params.set("sex", searchSex);
    navigate(`/members?${params.toString()}`);
  };

  const startUploadMatch = () => {
    if (!token) {
      navigate("/login");
      return;
    }
    uploadMatchRef.current?.click?.();
  };

  const onUploadMatchSelected = async (e) => {
    const file = e.target.files?.[0];
    // Clear so the user can re-select the exact same file
    e.target.value = "";

    if (!file) return;
    if (!token) {
      navigate("/login");
      return;
    }

    try {
      setIsProcessingSearch(true);
      // Pre-scale and normalize image client-side (~60-120KB JPEG)
      const dataUrl = await resizeImageFileToDataUrl(file, 640);

      try {
        sessionStorage.setItem("generatedImageUrl", dataUrl);
        sessionStorage.setItem("generatedGender", "Any");
      } catch (err) {
        console.warn("sessionStorage quota reached or unavailable:", err);
      }

      // Navigate to /results and include searchTimestamp so Results always re-runs
      navigate("/results", {
        state: {
          generatedImageUrl: dataUrl,
          gender: "Any",
          searchTimestamp: Date.now(),
        },
      });
    } catch (err) {
      console.error("Failed to process image for search:", err);
      alert(err?.message || "Failed to process image file");
    } finally {
      setIsProcessingSearch(false);
    }
  };

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        <Link
          to="/"
          className={`${styles.left} ${styles.brandLink}`}
          aria-label="Go to home"
        >
          <img
            src="/assets/logo.png"
            className={styles.logo}
            alt="FORENSIGHT Logo"
          />
          <h1 className={styles.title}>FORENSIGHT</h1>
        </Link>

        {token ? (
          <form className={styles.search} onSubmit={runMemberSearch}>
            <input
              className={styles.searchInput}
              placeholder="Search member by name"
              value={searchName}
              onChange={(e) => setSearchName(e.target.value)}
            />
            <select
              className={styles.searchSelect}
              value={searchSex}
              onChange={(e) => setSearchSex(e.target.value)}
              aria-label="Sex"
            >
              <option value="Any">Any</option>
              <option value="Male">Male</option>
              <option value="Female">Female</option>
              <option value="Other">Other</option>
            </select>
            <button
              className={styles.searchBtn}
              type="submit"
              disabled={!searchName.trim()}
            >
              Search
            </button>
          </form>
        ) : (
          <div />
        )}

        <div className={styles.actions}>
          <input
            ref={uploadMatchRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={onUploadMatchSelected}
          />

          <button
            type="button"
            className={`${styles.actionBtn} ${location.pathname === "/app" ? styles.activeActionBtn : ""}`}
            onClick={goGenerate}
            title={location.pathname === "/app" ? "Generate image from canvas sketch" : "Go to sketch generator"}
          >
            Generate Image
          </button>

          {token ? (
            <>
              <button
                type="button"
                className={`${styles.actionBtn} ${location.pathname === "/results" ? styles.activeActionBtn : ""}`}
                onClick={startUploadMatch}
                disabled={isProcessingSearch}
                title="Search suspect photo from local disk against criminal database"
              >
                {isProcessingSearch ? "Loading..." : "Search Image"}
              </button>

              {role === "ADMIN" && (
                <button
                  type="button"
                  className={`${styles.actionBtn} ${location.pathname === "/upload" ? styles.activeActionBtn : ""}`}
                  onClick={() => navigate("/upload")}
                  title="Enroll new criminal mugshot into database"
                >
                  Upload Image
                </button>
              )}

              <button
                type="button"
                className={styles.actionBtn}
                onClick={logout}
                title="Logout of FORENSIGHT"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className={`${styles.actionBtn} ${location.pathname === "/login" ? styles.activeActionBtn : ""}`}
                onClick={() => navigate("/login")}
              >
                Login
              </button>
              <button
                type="button"
                className={`${styles.actionBtn} ${location.pathname === "/signup" ? styles.activeActionBtn : ""}`}
                onClick={() => navigate("/signup")}
              >
                Signup
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
