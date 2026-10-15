/**
 * src/components/common/Avatar.tsx
 * Initials avatar that shows the user's own uploaded photo when available.
 * Falls back to initials when no photo is set (photo is optional).
 */
import { useEffect, useRef, useState, type FC } from 'react'
import { fetchMyPhoto, uploadProfilePhoto } from '../../services/authService'
import Icon from './Icon'

interface AvatarProps {
  name: string
  hasPhoto?: boolean
  /** Bump to reload the photo after an upload. */
  refreshKey?: number | string
  className?: string
  textClassName?: string
}

function initialsOf(name: string): string {
  return name.split(' ').map(w => w.charAt(0)).slice(0, 2).join('').toUpperCase() || '?'
}

export const Avatar: FC<AvatarProps> = ({
  name, hasPhoto, refreshKey, className = 'w-12 h-12 text-lg', textClassName = '',
}) => {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null)
  const objectUrl = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    if (!hasPhoto) {
      setPhotoUrl(null)
      return
    }
    fetchMyPhoto().then(url => {
      if (cancelled) return
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = url
      setPhotoUrl(url)
    })
    return () => { cancelled = true }
  }, [hasPhoto, refreshKey])

  useEffect(() => () => {
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
  }, [])

  if (photoUrl) {
    return (
      <img
        src={photoUrl}
        alt={name}
        className={`${className} rounded-full object-cover shrink-0 bg-slate-100`}
      />
    )
  }
  return (
    <span className={`avatar ${className} ${textClassName}`}>
      {initialsOf(name)}
    </span>
  )
}

interface AvatarWithUploadProps extends AvatarProps {
  onChanged: (hasPhoto: boolean) => void
}

/** Avatar with a small edit button to upload/replace the photo. */
export const AvatarWithUpload: FC<AvatarWithUploadProps> = ({ onChanged, ...props }) => {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    if (!['image/jpeg', 'image/png', 'image/jpg'].includes(file.type)) {
      setError('Only JPG or PNG photos are accepted.')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setError('Photo must be under 2 MB.')
      return
    }
    setError('')
    setUploading(true)
    try {
      await uploadProfilePhoto(file)
      onChanged(true)
    } catch {
      setError('Could not upload photo. Please try again.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="relative inline-block">
      <Avatar {...props} />
      <button
        type="button"
        title="Change profile photo"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="absolute -bottom-0.5 -right-0.5 w-6 h-6 rounded-full bg-white border border-slate-200
                   text-slate-500 hover:text-blue-700 flex items-center justify-center shadow-sm disabled:opacity-50"
      >
        <Icon name="plus" className="w-3.5 h-3.5" />
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".jpg,.jpeg,.png,image/jpeg,image/png"
        className="sr-only"
        onChange={e => handleFile(e.target.files?.[0])}
      />
      {error && <p className="form-error mt-1">{error}</p>}
    </div>
  )
}

export default Avatar
