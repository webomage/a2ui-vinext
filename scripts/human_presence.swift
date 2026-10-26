// Human-presence check for the mutating-recipe confirmation gate (T435 AC8).
//
// WHY: a typed "yes" proves a terminal, not a person. Agent harnesses hold terminals — agy answered a
// live `db-migrate` prompt through its own pty on 2026-09-17 — so the gate also asks macOS to verify
// the device owner (Touch ID, Apple Watch, or the login password in the system dialog). An agent can
// allocate a pty and write to it; it cannot touch the sensor or type into the secure system dialog.
//
// Built from source by confirm_step.py into a fresh temp dir on every use, deliberately: a cached
// binary outside the repo is a file anything could replace with one that exits 0.
//
// Usage:  w0m-confirm --check          → exit 0 if the policy can be evaluated, 2 if not (no dialog)
//         w0m-confirm "<reason text>"  → shows the dialog; exit 0 confirmed, 1 refused/cancelled,
//                                        2 unavailable
import Foundation
import LocalAuthentication

let args = CommandLine.arguments
let policy = LAPolicy.deviceOwnerAuthentication
let context = LAContext()
context.touchIDAuthenticationAllowableReuseDuration = 0  // never ride an earlier unlock

var availabilityError: NSError?
guard context.canEvaluatePolicy(policy, error: &availabilityError) else {
    let why = availabilityError?.localizedDescription ?? "unknown reason"
    FileHandle.standardError.write("unavailable: \(why)\n".data(using: .utf8)!)
    exit(2)
}
if args.count > 1 && args[1] == "--check" {
    print("available (biometry type \(context.biometryType.rawValue))")
    exit(0)
}
guard args.count > 1, !args[1].isEmpty else {
    FileHandle.standardError.write("usage: w0m-confirm --check | \"<reason>\"\n".data(using: .utf8)!)
    exit(2)
}

let done = DispatchSemaphore(value: 0)
var confirmed = false
var failure = ""
context.evaluatePolicy(policy, localizedReason: args[1]) { success, error in
    confirmed = success
    failure = error?.localizedDescription ?? ""
    done.signal()
}
done.wait()
if confirmed {
    exit(0)
}
FileHandle.standardError.write("not confirmed: \(failure)\n".data(using: .utf8)!)
exit(1)
