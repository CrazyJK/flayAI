"use client";

import { useEffect, useRef, useState, type DragEvent } from "react";

// 화면 전체 이미지 드래그&드롭 + 클립보드(캡처) 붙여넣기를 받아 onImage 로 전달하는 훅.
// 반환한 dropProps 를 페이지 루트 요소에 펼치고, dragOver 일 때 <DropOverlay /> 를 띄운다.
export function useImageDropPaste(onImage: (file: File) => void) {
  const [dragOver, setDragOver] = useState(false);
  const dragDepth = useRef(0); // 자식 위를 지날 때 dragleave 오작동 방지(깊이 카운트)
  const cbRef = useRef(onImage); // 최신 콜백 유지(전역 paste 리스너 재등록 방지)
  useEffect(() => {
    cbRef.current = onImage;
  }, [onImage]);

  const hasFiles = (e: DragEvent) =>
    Array.from(e.dataTransfer?.types ?? []).includes("Files");

  const dropProps = {
    onDragEnter: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current += 1;
      setDragOver(true);
    },
    onDragOver: (e: DragEvent) => {
      if (hasFiles(e)) e.preventDefault(); // drop 허용
    },
    onDragLeave: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      dragDepth.current = Math.max(0, dragDepth.current - 1);
      if (dragDepth.current === 0) setDragOver(false);
    },
    onDrop: (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth.current = 0;
      setDragOver(false);
      const img = Array.from(e.dataTransfer.files).find((f) => f.type.startsWith("image/"));
      if (img) cbRef.current(img);
    },
  };

  // 문서 전역 paste — 클립보드에 이미지가 있을 때만 가로챈다(텍스트 붙여넣기는 그대로)
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const item = Array.from(e.clipboardData?.items ?? []).find(
        (it) => it.kind === "file" && it.type.startsWith("image/")
      );
      const f = item?.getAsFile();
      if (f) {
        e.preventDefault();
        cbRef.current(f);
      }
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, []);

  return { dragOver, dropProps };
}

export function DropOverlay() {
  return (
    <div className="absolute inset-0 z-50 m-2 flex items-center justify-center rounded-2xl border-2 border-dashed border-blue-500 bg-blue-500/10 backdrop-blur-[1px] pointer-events-none">
      <div className="rounded-xl bg-card px-5 py-3 text-sm font-semibold text-blue-600 dark:text-blue-300 shadow-lg">
        여기에 놓으면 이미지 첨부
      </div>
    </div>
  );
}
