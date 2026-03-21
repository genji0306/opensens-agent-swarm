import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import type { Group } from "three";
import type { VisualAgent } from "@/gateway/types";
import { generateAvatar3dColor } from "@/lib/avatar-generator";
import { position2dTo3d } from "@/lib/position-allocator";
import { useOfficeStore } from "@/store/office-store";
import { ErrorIndicator } from "./ErrorIndicator";
import { SkillHologram } from "./SkillHologram";
import { ThinkingIndicator } from "./ThinkingIndicator";

interface AgentCharacterProps {
  agent: VisualAgent;
}

function easeOutBack(t: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
}

export function AgentCharacter({ agent }: AgentCharacterProps) {
  const { t } = useTranslation("common");
  const groupRef = useRef<Group>(null);
  const bodyRef = useRef<Group>(null);
  const spawnElapsed = useRef(0);
  const spawnDone = useRef(!agent.isSubAgent);
  const selectAgent = useOfficeStore((s) => s.selectAgent);
  const selectedAgentId = useOfficeStore((s) => s.selectedAgentId);
  const [hovered, setHovered] = useState(false);

  const isSelected = selectedAgentId === agent.id;
  const isSubAgent = agent.isSubAgent;
  const isOffline = agent.status === "offline";

  const isPlaceholder = agent.isPlaceholder;
  const isUnconfirmed = !agent.confirmed;
  const isWalking = agent.movement !== null;
  const tickMovement = useOfficeStore((s) => s.tickMovement);

  const baseColor = isSubAgent ? "#60a5fa" : generateAvatar3dColor(agent.id);
  const bodyOpacity = isPlaceholder ? 0.25 : isUnconfirmed ? 0.35 : isOffline ? 0.4 : isSubAgent ? 0.6 : 1;
  const displayColor = isOffline || isPlaceholder || isUnconfirmed ? "#6b7280" : baseColor;

  const [targetX, , targetZ] = position2dTo3d(agent.position);

  useFrame((state, delta) => {
    if (!groupRef.current) {
      return;
    }
    const t = state.clock.elapsedTime;

    // Spawn scale-in animation for sub-agents (800ms, easeOutBack)
    if (!spawnDone.current) {
      spawnElapsed.current += delta;
      const progress = Math.min(spawnElapsed.current / 0.8, 1);
      const scale = easeOutBack(progress);
      groupRef.current.scale.setScalar(scale);
      if (progress >= 1) {
        spawnDone.current = true;
      }
      return;
    }

    // Walking animation: tick store, use slower lerp for visible movement
    if (isWalking) {
      tickMovement(agent.id, delta);

      const curAgent = useOfficeStore.getState().agents.get(agent.id);
      if (curAgent) {
        const [wx, , wz] = position2dTo3d(curAgent.position);
        const walkLerp = Math.min(2.5 * delta, 0.1);
        const pos = groupRef.current.position;
        pos.x += (wx - pos.x) * walkLerp;
        pos.z += (wz - pos.z) * walkLerp;

        // Walk body sway ±0.08 rad at 8Hz
        if (bodyRef.current) {
          bodyRef.current.rotation.z = Math.sin(t * 8 * Math.PI * 2) * 0.08;
          // Walk bounce
          bodyRef.current.position.y = Math.abs(Math.sin(t * 8)) * 0.03;
        }
      }
    } else {
      // Normal smooth position lerp
      const lerpFactor = 1 - Math.pow(0.05, delta);
      const pos = groupRef.current.position;
      pos.x += (targetX - pos.x) * lerpFactor;
      pos.z += (targetZ - pos.z) * lerpFactor;

      // Idle breathing
      if (bodyRef.current) {
        bodyRef.current.position.y = Math.sin(t * 2) * 0.02;
        bodyRef.current.rotation.z = 0;
      }
    }

    if (isSubAgent && !isPlaceholder) {
      const pulse = 1.0 + Math.sin(t * 3) * 0.05;
      groupRef.current.scale.setScalar(pulse);
    }
  });

  return (
    <group
      ref={groupRef}
      position={[targetX, 0, targetZ]}
      scale={isSubAgent && !spawnDone.current ? 0 : 1}
      onClick={(e) => {
        e.stopPropagation();
        if (!isPlaceholder) selectAgent(agent.id);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        if (!isPlaceholder) {
          setHovered(true);
          document.body.style.cursor = "pointer";
        }
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "auto";
      }}
    >
      <group ref={bodyRef}>
        <mesh position={[0, 0.35, 0]} castShadow>
          <capsuleGeometry args={[0.15, 0.4, 8, 16]} />
          <meshStandardMaterial
            color={displayColor}
            transparent={bodyOpacity < 1}
            opacity={bodyOpacity}
          />
        </mesh>

        <mesh position={[0, 0.7, 0]} castShadow>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshStandardMaterial
            color={displayColor}
            transparent={bodyOpacity < 1}
            opacity={bodyOpacity}
          />
        </mesh>
      </group>

      {agent.status === "thinking" && <ThinkingIndicator />}
      {agent.status === "tool_calling" && agent.currentTool && (
        <SkillHologram tool={{ name: agent.currentTool.name }} position={[0.3, 0.5, -0.3]} />
      )}
      {agent.status === "error" && <ErrorIndicator />}

      {/* Speaking indicator — collapsed icon; full bubble shown via 2D overlay */}
      {agent.status === "speaking" && agent.speechBubble && (
        <Html position={[0, 1.0, 0]} center transform={false}>
          <div className="flex items-center justify-center">
            <div className="relative flex h-6 w-6 items-center justify-center rounded-full bg-purple-500 text-white shadow-md">
              <svg viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3">
                <path
                  fillRule="evenodd"
                  d="M3.43 2.524A41.29 41.29 0 0110 2c2.236 0 4.43.18 6.57.524 1.437.231 2.43 1.49 2.43 2.902v5.148c0 1.413-.993 2.67-2.43 2.902a41.102 41.102 0 01-3.55.414c-.28.02-.521.18-.643.413l-1.712 3.293a.75.75 0 01-1.33 0l-1.713-3.293a.783.783 0 00-.642-.413 41.108 41.108 0 01-3.55-.414C1.993 13.245 1 11.986 1 10.574V5.426c0-1.413.993-2.67 2.43-2.902z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-purple-300 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-purple-400" />
              </span>
            </div>
          </div>
        </Html>
      )}

      {isSelected && (
        <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.25, 0.3, 32]} />
          <meshStandardMaterial
            color="#3b82f6"
            emissive="#3b82f6"
            emissiveIntensity={0.5}
            transparent
            opacity={0.8}
          />
        </mesh>
      )}

      {hovered && (
        <Html position={[0, 1.1, 0]} center transform={false} style={{ pointerEvents: "none" }}>
          <div className="pointer-events-none whitespace-nowrap rounded bg-gray-800 px-2 py-1 text-[11px] text-white shadow">
            {agent.name} — {t(`agent.statusLabels.${agent.status}`)}
          </div>
        </Html>
      )}
    </group>
  );
}
