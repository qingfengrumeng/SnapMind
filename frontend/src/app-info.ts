import appConfig from '../../src-tauri/tauri.conf.json'

// Set the project's own repository here when it is published.
export const appInfo = {
  name: appConfig.productName,
  version: appConfig.version,
  repositoryUrl: '',
}
