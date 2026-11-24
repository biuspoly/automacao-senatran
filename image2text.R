library(tesseract)
library(magick)
library(png)


# Obter o caminho do arquivo de imagem via argumento de linha de comando
args <- commandArgs(trailingOnly = TRUE)
caminho_imagem <- args[1]
uf_R <- args[2]
imagem <- image_read(caminho_imagem)

if (uf_R=='ES' || uf_R=='PI' || uf_R=='PA'){
  
  eng <- tesseract("eng")
  text <- tesseract::ocr(imagem, engine = eng)
  cat(text)
  
}
if (uf_R=='MS'){
  
  # Leitura da imagem
  teste = png::readPNG(caminho_imagem)
  
  
  
  # Definir as cores RGB que queremos manter (preto, azul, vermelho, laranja)
  cores_desejadas <- list(
    c(228/255,106/255,98/255),
    c(153/255,75/255,250/255),
    c(27/255, 117/255, 226/255)
  )
  
  # Função para verificar se a cor está na lista de cores desejadas com uma margem de tolerância
  eh_cor_desejada <- function(cor) {
    for (cor_desejada in cores_desejadas) {
      # Verifica se a cor é "aproximadamente" a cor desejada (com uma tolerância)
      if (all(abs(cor - cor_desejada) < 0.3)) {
        return(TRUE)
      }
    }
    return(FALSE)
  }
  
  # Percorrendo a matriz para substituir os valores não correspondentes
  for (i in 1:dim(teste)[1]) {
    for (j in 1:dim(teste)[2]) {
      # Pega o valor RGB da célula (i, j)
      cor_pixel <- teste[i, j, ]
      
      # Se a cor não for uma das cores desejadas, substitua por preto (RGB(0, 0, 0))
      if (!eh_cor_desejada(cor_pixel)) {
        teste[i, j, ] <- c(1, 1, 1)  # Substitui por preto
      }
    }
  }
  
  
  
  # Salva a matriz modificada como uma nova imagem
  # writePNG(teste, "imagem_modificada.png")

  
  # Exibe a matriz modificada
 
  eng = tesseract::tesseract("eng")
  teste = magick::image_read(teste)
  teste1 = image_crop(teste,"30x100+0+0")
  teste2 = image_crop(teste,"30x100+35+0")
  teste3 = image_crop(teste,"30x100+70+0")
  teste4 = image_crop(teste,"30x100+105+0")
  
  texto1 = ocr(teste1)
  texto2 = ocr(teste2)
  texto3 = ocr(teste3)
  texto4 = ocr(teste4)
  
  cat(gsub("[^A-Z]","",gsub("\n","",paste0(texto1,texto2,texto3,texto4))))
  
}
